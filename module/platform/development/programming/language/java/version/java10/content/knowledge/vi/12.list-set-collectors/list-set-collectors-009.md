# So sánh collector không sửa được với `collectingAndThen` kết hợp lớp bọc chỉ đọc (Java 10+)

## 1. Bối cảnh và mục tiêu

Trong Java Streams, có hai cách thường gặp để thu thập phần tử thành `List` hoặc `Set` mà người nhận kết quả **không thể sửa thông qua reference được trả về**:

**Cách trực tiếp từ Java 10:**

```java
var names = java.util.stream.Stream.of("An", "Binh")
        .collect(java.util.stream.Collectors.toUnmodifiableList());

var roles = java.util.stream.Stream.of("USER", "ADMIN")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

**Cách ghép collector với một bước hoàn thiện (*finisher*):**

```java
var names = java.util.stream.Stream.of("An", "Binh")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toList(),
                java.util.Collections::unmodifiableList));

var roles = java.util.stream.Stream.of("USER", "ADMIN")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toSet(),
                java.util.Collections::unmodifiableSet));
```

Hai cách trên đều có thể tạo một collection mà thao tác `add`, `remove` hoặc `set`/`clear` qua kết quả bị từ chối, nhưng **chúng không hoàn toàn tương đương về hợp đồng**. Sự khác biệt nằm ở:

- Collector trực tiếp Java 10 **quy định rõ không nhận phần tử `null`**.
- `collectingAndThen` dùng kết quả của một **collector bên trong**, rồi áp dụng finisher: null, thứ tự, loại collection và khả năng chia sẻ backing phụ thuộc cách ghép các thành phần.
- `Collections.unmodifiableList` và `Collections.unmodifiableSet` trả về **view không sửa được của collection bên dưới**, không tự tạo snapshot cấu trúc độc lập như `List.copyOf`/`Set.copyOf`.
- Với `Set`, thứ tự duyệt và cách xử lý các phần tử trùng có thể khác theo collector downstream.

Từ Java 10, `Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` là các API chuẩn. `Collectors.collectingAndThen(...)` có từ Java 8 và **vẫn được hỗ trợ, vẫn hữu ích** khi cần bước hoàn thiện tùy biến; không phải API bị loại bỏ hoặc legacy.

## 2. Nhận diện các API và chữ ký

Trong `java.util.stream.Collectors`, hai collector trực tiếp có chữ ký khái quát:

```java
static <T> Collector<T, ?, List<T>> toUnmodifiableList()
static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()
```

Khi Stream đã có kiểu phần tử `T`, kết quả lần lượt là `List<T>` và `Set<T>`. `var` suy luận kiểu tĩnh này từ biểu thức `collect(...)`, không suy luận tên lớp triển khai bên trong.

Trong khi đó, `collectingAndThen` có chữ ký:

```java
static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher)
```

Phân tích:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử đi vào quá trình gom. |
| `A` | Kiểu trạng thái tích lũy trung gian của downstream collector. |
| `R` | Kiểu **kết quả** do downstream collector tạo ra trước finisher. |
| `RR` | Kiểu **kết quả cuối cùng** sau khi chạy finisher. |
| `downstream` | Collector làm công việc thu thập thực tế, ví dụ `toList()` hoặc `toCollection(ArrayList::new)`. |
| `finisher` | Hàm biến kết quả `R` thành kết quả `RR`, ví dụ `Collections::unmodifiableList` hoặc `List::copyOf`. |

Sơ đồ:

```text
Stream<T>
   |
   v
downstream collector (tích lũy phần tử)
   |
   v
R: List<T> hoặc Set<T> của downstream
   |
   v
finisher: Collections.unmodifiableList/Set
   |
   v
RR: unmodifiable view (kết quả trả cho bên gọi)
```

**Điểm mấu chốt:** `collectingAndThen` **không có sẵn một chính sách “bất biến”**. Nó đơn thuần thực hiện **một phép biến đổi cuối**. Tính không sửa được chỉ xuất hiện vì ta truyền `Collections::unmodifiableList`/`Collections::unmodifiableSet` làm finisher.

### `toList()`/`toSet()` không hứa kiểu hay khả năng sửa

Tài liệu hiện hành của `Collectors.toList()` và `Collectors.toSet()` **không bảo đảm** loại lớp triển khai, khả năng thay đổi, khả năng tuần tự hóa hoặc tính an toàn luồng của kết quả. Vì vậy không nên tuyên bố `Collectors.toList()` **luôn** trả về một `ArrayList` có thể sửa.

Muốn downstream **chắc chắn** là một collection xác định, hãy chọn `Collectors.toCollection(Supplier)`:

```java
Collectors.toCollection(ArrayList::new)
Collectors.toCollection(LinkedHashSet::new)
```

Những dòng trên là các biểu thức minh họa trong ngữ cảnh đã import `java.util` và `java.util.stream`. Ở ví dụ đầy đủ, ta sẽ dùng cách này để quan sát rõ sự khác nhau giữa **view** và **snapshot**.

## 3. Bảng so sánh nhanh

| Tiêu chí | `toUnmodifiableList()` / `toUnmodifiableSet()` | `collectingAndThen(downstream, Collections::unmodifiableList/Set)` |
| --- | --- | --- |
| Xuất hiện | Java 10 | `collectingAndThen` từ Java 8; các API vẫn dùng được trên JDK hiện nay |
| Mục đích | Trực tiếp tạo kết quả unmodifiable | Gom bằng downstream, rồi biến đổi kết quả bằng finisher |
| Có cho sửa qua collection trả về? | Không | Không, khi finisher đúng là lớp bọc unmodifiable |
| `null` ở đầu vào | **Không chấp nhận**; ném `NullPointerException` | **Phụ thuộc downstream**; lớp bọc không mặc định cấm `null` |
| Thứ tự của List | Giữ **encounter order** của stream có thứ tự | Phụ thuộc downstream; `toList`/`toCollection(ArrayList::new)` giữ encounter order |
| Thứ tự của Set | Collector **unordered**; không hứa thứ tự duyệt | Phụ thuộc Set bên trong; có thể giữ thứ tự duyệt của `LinkedHashSet` nếu chọn loại này |
| Phần tử trùng trong Set | Loại trùng; nếu nhiều phần tử bằng nhau thì chọn **một phần tử bất kỳ** trong nhóm | Phụ thuộc `Set` bên trong; `LinkedHashSet` thông thường giữ phần tử được thêm đầu tiên theo thứ tự gom |
| Mô hình backing | Kết quả unmodifiable theo hợp đồng collector; không hứa lớp nội bộ cụ thể | `Collections.unmodifiableX` là **view** được backing bởi kết quả downstream |
| Có tự deep-copy object phần tử? | Không | Không |
| Thêm bước hoàn thiện tùy biến? | Không trực tiếp qua chính collector | Có: bất kỳ finisher hợp lệ nào, ví dụ `List::copyOf`, chuẩn hóa hoặc tạo DTO |

Bảng so sánh đang nói tới các **collector cụ thể** được nêu, không phải mọi biến thể có thể truyền vào `collectingAndThen`.

## 4. List: hai kết quả giống nội dung nhưng không cùng cơ chế

### 4.1. Dùng `Collectors.toUnmodifiableList`

```java
var direct = java.util.stream.Stream.of("A", "B", "A")
        .collect(java.util.stream.Collectors.toUnmodifiableList());

// direct là List<String>, nội dung theo encounter order: [A, B, A].
// direct.add("C") sẽ ném UnsupportedOperationException.
```

Collector giữ **thứ tự gặp phần tử** của stream có thứ tự và cho phép **phần tử trùng**, vì kết quả là `List`. Việc `add` bị từ chối là bảo đảm của unmodifiable List. Từ Java 10 đến các bản Java hiện hành, collector này vẫn được hỗ trợ.

### 4.2. Dùng `collectingAndThen` với lớp bọc

```java
var wrapped = java.util.stream.Stream.of("A", "B", "A")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new),
                java.util.Collections::unmodifiableList));
```

Đọc theo thứ tự:

1. `toCollection(ArrayList::new)` tạo một `ArrayList<String>` để gom phần tử theo encounter order.
2. `collectingAndThen` chạy finisher `Collections.unmodifiableList` trên collection đã gom.
3. Kết quả là một `List<String>` không sửa được **qua wrapper**.
4. Wrapper vẫn **backed by** `ArrayList` mà downstream tạo, không phải một snapshot tách biệt theo ý nghĩa của `List.copyOf`.

Hai List từ `direct` và `wrapped` ở ví dụ này **bằng nhau về nội dung** (`equals` là `true`), nhưng không nên viết test phụ thuộc vào lớp triển khai hoặc identity của chúng.

### 4.3. Trường hợp hay dùng, nhưng cần hiểu giới hạn

API `Collectors` minh họa idiom:

```java
var wrapped = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toList(),
                java.util.Collections::unmodifiableList));
```

Đây là cách viết **hợp lệ và vẫn hiện hành**. Tuy nhiên, `toList()` không cam kết luôn trả `ArrayList` hay luôn cho sửa; do đó **không suy luận dựa trên class cụ thể**. `Collections.unmodifiableList` chỉ cần một `List` để trả về view không sửa được. Nếu cần chắc chắn loại downstream, dùng `toCollection(ArrayList::new)` như phần trước.

## 5. Set: trùng lặp, thứ tự và ý nghĩa của downstream

### 5.1. Collector trực tiếp `toUnmodifiableSet`

```java
var directSet = java.util.stream.Stream.of("B", "A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

Bảo đảm quan trọng:

- Kết quả có **hai phần tử khác nhau theo `equals`**: `"A"` và `"B"`.
- Không thể `add`, `remove` hoặc `clear` qua kết quả.
- Đây là **unordered collector**; không hứa thứ tự duyệt `"B", "A"` hay `"A", "B"`.
- Với hai object khác nhau nhưng `equals` trả `true`, nếu có duplicate, API nói một object **bất kỳ** trong nhóm có thể được giữ. Đừng dựa vào việc collector luôn giữ bản xuất hiện đầu tiên.

Vì thứ tự duyệt không được bảo đảm, **không đưa `directSet.toString()` vào expected stdout cố định** nếu cần kết quả nhất quán giữa các bản JDK.

### 5.2. Lớp bọc Set từ `collectingAndThen`

```java
var wrappedSet = java.util.stream.Stream.of("B", "A", "B")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.LinkedHashSet::new),
                java.util.Collections::unmodifiableSet));
```

Ở đây ta **chủ động chọn `LinkedHashSet`** làm collection đích. `LinkedHashSet` có thứ tự duyệt theo thứ tự chèn trong tình huống này, loại các phần tử trùng theo `equals`. Wrapper `Collections.unmodifiableSet` đọc qua Set bên trong, nên giữ hành vi duyệt của backing Set.

Nếu chỉ dùng:

```java
Collectors.collectingAndThen(
        Collectors.toSet(),
        Collections::unmodifiableSet)
```

thì bạn **không được bảo đảm** một lớp Set hay thứ tự duyệt cụ thể từ `toSet()`. Wrapper **không tự bổ sung** thứ tự cho kết quả downstream.

**Lưu ý thiết kế:** nếu yêu cầu hợp đồng API về thứ tự là quan trọng, hãy cân nhắc công bố một `List` đã được sắp xếp hoặc sử dụng loại Set có hợp đồng thứ tự rõ ràng ở tầng thiết kế, không dựa vào thứ tự tình cờ của collector `toUnmodifiableSet`.

## 6. Khác biệt quan trọng nhất khi có `null`

### 6.1. Hai collector trực tiếp Java 10 cấm `null`

```java
// Cả hai lời gọi này đều ném NullPointerException:
java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
```

`Collectors.toUnmodifiableList` và `Collectors.toUnmodifiableSet` có **quy tắc loại bỏ `null` bằng ngoại lệ**. `null` không bị tự động bỏ qua; nếu không muốn `null`, có thể lọc trước khi collect:

```java
var withoutNulls = java.util.stream.Stream.<String>of("A", null)
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Dòng trên tạo List `["A"]`. Việc lọc `null` phải là quyết định có chủ đích của nghiệp vụ, không phải một quy tắc mặc định của `collect`.

### 6.2. Lớp bọc không tự cấm `null`

`ArrayList` và `LinkedHashSet` đều chấp nhận `null`. Vì thế, khi chọn chúng làm downstream, `Collections.unmodifiableList/Set` **không tự xóa hay từ chối** `null` đã được tích lũy:

```java
var listWithNull = java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new),
                java.util.Collections::unmodifiableList));

System.out.println(listWithNull.contains(null)); // true
```

Tương tự:

```java
var setWithNull = java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.LinkedHashSet::new),
                java.util.Collections::unmodifiableSet));

System.out.println(setWithNull.contains(null)); // true
```

Đây **không phải** quy tắc “`collectingAndThen` luôn cho phép `null`”. Nếu downstream hoặc finisher tự từ chối `null`, lời gọi vẫn có thể thất bại. **Chính collector bên trong và finisher quyết định** chính sách này.

Vì vậy, **không thay máy móc** `collectingAndThen(toCollection(ArrayList::new), Collections::unmodifiableList)` bằng `toUnmodifiableList()` nếu dữ liệu hiện tại có thể chứa `null` và chương trình được thiết kế để giữ nó.

## 7. Unmodifiable view khác với snapshot

### 7.1. `Collections.unmodifiableList` là view của backing List

`Collections.unmodifiableList(list)` trả về một **view không cho thay đổi qua view**, nhưng những thay đổi trên `list` qua một reference khác vẫn có thể quan sát được qua view.

```java
var backing = new java.util.ArrayList<>(
        java.util.List.of("X", "Y"));
var view = java.util.Collections.unmodifiableList(backing);

backing.add("Z");
System.out.println(view); // [X, Y, Z]
```

`view.add("W")` bị từ chối, nhưng `backing.add("Z")` vẫn hợp lệ. Cơ chế tương ứng áp dụng cho `Collections.unmodifiableSet` với Set backing của nó.

### 7.2. Trong một lần collect bình thường, backing thường không bị lộ ra

Khi dùng:

```java
var wrapped = java.util.stream.Stream.of("X", "Y")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new),
                java.util.Collections::unmodifiableList));
```

downstream tích lũy vào danh sách nội bộ và finisher bọc danh sách ấy. **Nếu chương trình không giữ lại reference đến backing**, bên gọi thông thường chỉ nhận `wrapped` và không thể sửa trực tiếp collection bên dưới qua `wrapped`.

Vì vậy, không nên tuyên bố “cứ dùng `collectingAndThen + unmodifiableList` là nội dung chắc chắn sẽ bị thay đổi từ bên ngoài”. Đây là **rủi ro nếu backing còn được truy cập bằng reference khác**, không phải hành vi tất yếu.

### 7.3. Ví dụ cố ý giữ backing để chứng minh khác biệt

```java
java.util.concurrent.atomic.AtomicReference<java.util.List<String>>
        backingRef = new java.util.concurrent.atomic.AtomicReference<>();

var view = java.util.stream.Stream.of("X", "Y")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new),
                list -> {
                    backingRef.set(list); // Cố ý làm lộ backing để minh họa
                    return java.util.Collections.unmodifiableList(list);
                }));

backingRef.get().add("Z");
System.out.println(view); // [X, Y, Z]
```

Đây là **đoạn minh họa đặt bên trong một phương thức**, không phải mã độc lập; ví dụ đầy đủ ở phần sau đã kiểm thử hành vi này. `AtomicReference` được dùng chỉ để giữ tham chiếu backing ngoài lambda, không biến view thành thread-safe.

**Đừng dùng cách cố ý làm lộ backing này trong thiết kế API nếu cần kết quả ổn định.** Nó chỉ minh họa rằng finisher `Collections.unmodifiableList` không phải thao tác tạo snapshot.

### 7.4. Nếu muốn snapshot độc lập: `List.copyOf`/`Set.copyOf`

Có thể dùng finisher sao chép:

```java
var snapshot = java.util.stream.Stream.of("X", "Y")
        .collect(java.util.stream.Collectors.collectingAndThen(
                java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new),
                java.util.List::copyOf));
```

`List.copyOf` (Java 10+) tạo List không sửa được có nội dung không phản ánh các thay đổi cấu trúc của collection đầu vào **sau khi tạo bản sao**. Nó **cấm `null`**, khác wrapper với `ArrayList` đã cho phép `null`.

Tương tự, `Set.copyOf` giúp tạo Set không sửa được từ Set/Collection bên trong. Tuy nhiên, với Set có object trùng theo `equals`, quy tắc lựa chọn object giữ lại và thứ tự duyệt cần được đọc đúng theo hợp đồng API. Nếu muốn kết quả tự nhiên và ngắn gọn, nhiều bài toán chỉ cần `toUnmodifiableList` hoặc `toUnmodifiableSet`.

**Không deep copy:** dù là collector trực tiếp, wrapper hay `copyOf`, các object phần tử mutable vẫn có thể bị thay đổi trạng thái ở nơi khác. Đây là ranh giới chung của “collection không sửa được”, không nên nhầm với bất biến sâu của từng phần tử.

## 8. Chương trình Java 17+ hoàn chỉnh và kết quả kiểm chứng

Lưu toàn bộ mã dưới đây vào **`CollectorWrapperDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorWrapperDemo {
    public static void main(String[] args) {
        var directList = Stream.of("A", "B", "A")
                .collect(Collectors.toUnmodifiableList());
        var wrappedList = Stream.of("A", "B", "A")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        Collections::unmodifiableList));

        System.out.println("listEqual=" + directList.equals(wrappedList));
        System.out.println("listOrder=" + directList);

        var directSet = Stream.of("B", "A", "B")
                .collect(Collectors.toUnmodifiableSet());
        var wrappedSet = Stream.of("B", "A", "B")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(LinkedHashSet::new),
                        Collections::unmodifiableSet));

        System.out.println("setEqual=" + directSet.equals(wrappedSet));
        System.out.println("setSize=" + directSet.size());

        try {
            directList.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("directListAddRejected=true");
        }
        try {
            wrappedSet.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("wrappedSetAddRejected=true");
        }
        try {
            Stream.<String>of("A", null)
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            System.out.println("directListNullRejected=true");
        }

        var wrapperWithNull = Stream.<String>of("A", null)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        Collections::unmodifiableList));
        System.out.println(
                "wrapperListKeepsNull=" + wrapperWithNull.contains(null));

        try {
            Stream.<String>of("A", null)
                    .collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException expected) {
            System.out.println("directSetNullRejected=true");
        }

        var wrapperSetWithNull = Stream.<String>of("A", null)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(LinkedHashSet::new),
                        Collections::unmodifiableSet));
        System.out.println(
                "wrapperSetKeepsNull=" + wrapperSetWithNull.contains(null));

        // Minh họa cố ý làm lộ backing, không phải cách thiết kế API nên dùng.
        AtomicReference<List<String>> backing = new AtomicReference<>();
        var exposedView = Stream.of("X", "Y")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        list -> {
                            backing.set(list);
                            return Collections.unmodifiableList(list);
                        }));
        backing.get().add("Z");
        System.out.println(
                "exposedViewAfterBackingChange=" + exposedView);

        var snapshot = Stream.of("X", "Y")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        List::copyOf));
        System.out.println("snapshot=" + snapshot);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 CollectorWrapperDemo.java
java CollectorWrapperDemo
```

**Stdout chính xác** trên Java 17+:

```text
listEqual=true
listOrder=[A, B, A]
setEqual=true
setSize=2
directListAddRejected=true
wrappedSetAddRejected=true
directListNullRejected=true
wrapperListKeepsNull=true
directSetNullRejected=true
wrapperSetKeepsNull=true
exposedViewAfterBackingChange=[X, Y, Z]
snapshot=[X, Y]
```

Giải thích:

1. Hai collector List có cùng nội dung và thứ tự; `List.equals` cho `true`. Duplicate `"A"` vẫn được giữ trong List.
2. Hai collector Set loại trùng `"B"` và có cùng tập phần tử; `Set.equals` cho `true` và kích thước là `2`. Không in `directSet` vì thứ tự duyệt của nó không được bảo đảm.
3. `directList.add` và `wrappedSet.add` đều ném `UnsupportedOperationException`.
4. `toUnmodifiableList`/`toUnmodifiableSet` từ chối `null`; các wrapper dùng downstream `ArrayList`/`LinkedHashSet` trong ví dụ vẫn có thể chứa `null`.
5. `exposedViewAfterBackingChange` cho thấy thay đổi qua reference đến backing làm thay đổi nội dung quan sát qua wrapper.
6. `List::copyOf` tạo snapshot không phản ánh sửa đổi cấu trúc của đầu vào sau khi tạo; ví dụ `snapshot` có `[X, Y]`.

Ví dụ này chỉ dùng các API hiện hành và cú pháp ổn định, không cần preview feature.

## 9. Khi nào chọn cách nào?

### Ưu tiên collector trực tiếp Java 10

Chọn:

```java
var result = stream.collect(Collectors.toUnmodifiableList());
```

hoặc:

```java
var result = stream.collect(Collectors.toUnmodifiableSet());
```

khi muốn một kết quả không sửa được, **chấp nhận chính sách không có `null`**, và không cần một bước hoàn thiện đặc biệt. Đây là cách viết ngắn gọn, biểu đạt mục đích rõ ràng. Trong ví dụ, `stream` giả định là biến `Stream<T>` đã có, và `Collectors` được import.

### Chọn `collectingAndThen` khi finisher có lý do cụ thể

Ví dụ:

```java
var result = stream.collect(Collectors.collectingAndThen(
        Collectors.toCollection(ArrayList::new),
        Collections::unmodifiableList));
```

Cách ghép này thích hợp nếu cần **kiểm soát downstream collection**, chẳng hạn giữ cho phép `null` hoặc muốn chọn lớp `ArrayList`/`LinkedHashSet` trước khi trả view. Tuy nhiên, hãy ghi nhớ wrapper là **view**, không phải snapshot.

Nếu cần đảm bảo snapshot và không có `null`, cân nhắc:

```java
var result = stream.collect(Collectors.collectingAndThen(
        Collectors.toCollection(ArrayList::new),
        List::copyOf));
```

Không nên biến `collectingAndThen` thành bước dư thừa chỉ vì “mã cũ từng viết như vậy”: nếu không cần thêm chính sách hoặc finisher tùy chỉnh, collector trực tiếp thường dễ đọc hơn. **Điều đó không khiến `collectingAndThen` trở thành legacy**.

### Khi cần kết quả có thể sửa được

Không sử dụng các collector unmodifiable nếu nơi nhận cần gọi `add`/`remove`. Dùng rõ ràng:

```java
var editable = stream.collect(
        Collectors.toCollection(ArrayList::new));
```

Đoạn mã này cố ý cung cấp `ArrayList` có thể sửa được. `Collectors.toList()` không có bảo đảm khả năng sửa trong hợp đồng, nên không thay thế mặc định nếu yêu cầu là bắt buộc modifiable.

## 10. Các lỗi phổ biến

**Lỗi 1 — Coi wrapper và collector trực tiếp là giống hệt nhau.**  
Sai: `toUnmodifiableList/Set` cấm `null`; wrapper theo downstream có thể cho `null`, và wrapper là view của collection bên trong.

**Lỗi 2 — Tưởng `collectingAndThen` tự tạo immutable collection.**  
Sai: finisher quyết định kết quả. Ví dụ `collectingAndThen(toList(), Function.identity())` không tự thêm chính sách unmodifiable.

**Lỗi 3 — Tưởng `Collections.unmodifiableList` tạo bản sao độc lập.**  
Sai: nó bọc backing. Nếu backing còn bị thay đổi từ reference khác, view thấy thay đổi. Dùng `List.copyOf` nếu cần snapshot cấu trúc.

**Lỗi 4 — Khẳng định `Collectors.toList` luôn cho `ArrayList` có thể sửa.**  
Sai: đặc tả không bảo đảm. Dùng `toCollection(ArrayList::new)` khi loại collection và khả năng sửa quan trọng.

**Lỗi 5 — Dựa vào thứ tự duyệt `toUnmodifiableSet`.**  
Sai: đây là unordered collector. Nếu yêu cầu thứ tự, chọn downstream có hợp đồng như `LinkedHashSet` hoặc tạo danh sách đã sắp xếp.

**Lỗi 6 — Với Set, giả định luôn giữ object trùng đầu tiên.**  
Sai với `toUnmodifiableSet`: khi các phần tử bằng nhau theo `equals`, API cho phép giữ một đại diện bất kỳ. Muốn hành vi khác, dùng downstream có hợp đồng phù hợp và kiểm thử trên stream có thứ tự.

**Lỗi 7 — Cho rằng unmodifiable đồng nghĩa các phần tử bất biến sâu.**  
Sai: phần tử mutable vẫn thay đổi trạng thái được. Hãy thiết kế kiểu phần tử bất biến nếu cần tính bất biến toàn bộ dữ liệu.

**Lỗi 8 — Lấy kết quả unmodifiable làm bằng chứng an toàn luồng tuyệt đối.**  
Sai: nếu backing của view bị sửa đồng thời, hoặc phần tử có trạng thái mutable, cần xem lại an toàn luồng và cách công bố dữ liệu. Finisher không phải primitive đồng bộ hóa.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.of("A","B").collect(toUnmodifiableList())` khác gì `collectingAndThen(toList(), unmodifiableList)`?  
**Đáp án:** Cùng có thể cho List không sửa được với thứ tự `["A", "B"]`. Nhưng collector trực tiếp cấm `null` và không công bố backing tùy biến; cách hai phụ thuộc downstream `toList`, rồi bọc view bằng `Collections.unmodifiableList`.

**Câu 2.** `toUnmodifiableSet` có hứa giữ `"B"` trước `"A"` khi stream lần lượt gặp `"B", "A"` không?  
**Đáp án:** Không. Nó là unordered collector; không suy ra thứ tự duyệt từ thứ tự đầu vào.

**Câu 3.** Vì sao wrapper kết hợp `ArrayList` có thể giữ `null` còn collector trực tiếp lại ném ngoại lệ?  
**Đáp án:** `ArrayList` cho phép `null` và `Collections.unmodifiableList` chỉ bọc view; `Collectors.toUnmodifiableList` có hợp đồng riêng từ chối phần tử `null`.

**Câu 4.** Khi đã thu gom xong với `collectingAndThen`, người gọi có luôn sửa được backing List không?  
**Đáp án:** Không. Trong pipeline thông thường, backing không bị lộ; chỉ nếu có reference khác đến collection bên dưới (do cố ý làm lộ hoặc thiết kế kém) thì thay đổi từ reference đó mới được phản ánh qua view.

**Câu 5.** Muốn snapshot không sửa được thay vì view có thể dùng finisher nào?  
**Đáp án:** `List::copyOf` (hoặc `Set::copyOf` khi phù hợp). Nó không phản ánh sửa đổi cấu trúc nguồn sau khi tạo và cấm `null`, nhưng không deep-copy phần tử.

**Câu 6.** `Collectors.toList()` có phải luôn trả về collection có thể `add` không?  
**Đáp án:** Không có bảo đảm về mutability. Khi cần mutable `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`.

## 12. Tóm tắt

1. Từ **Java 10**, `Collectors.toUnmodifiableList` và `Collectors.toUnmodifiableSet` tạo kết quả **unmodifiable, không nhận `null`**. List giữ encounter order; Set là unordered.
2. `Collectors.collectingAndThen(downstream, finisher)` là bộ ghép vẫn hiện hành: thu thập bằng downstream rồi chạy một finisher.
3. `Collections.unmodifiableList/Set` là **unmodifiable view**, không mặc nhiên là bản sao cấu trúc; chính sách `null`, kiểu backing và thứ tự Set phụ thuộc downstream.
4. Nếu cần snapshot thay vì view, `collectingAndThen(..., List::copyOf)` là một lựa chọn; có thể dùng collector trực tiếp nếu chỉ cần unmodifiable và không có `null`.
5. `Collectors.toList/toSet` không hứa lớp triển khai hay khả năng sửa; dùng `toCollection` khi cần kiểm soát cấu trúc nội bộ.
6. **Unmodifiable không đồng nghĩa deep-immutable hoặc tự động thread-safe**. Đừng phụ thuộc lớp nội bộ, identity hoặc thứ tự Set không được đặc tả.

## Tài liệu chính thức còn áp dụng

- Java SE 26 — `Collectors.toUnmodifiableList`, `Collectors.toUnmodifiableSet`, `collectingAndThen`, `toList`, `toSet` và `toCollection`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- Java SE 26 — `Collections.unmodifiableList` / `Collections.unmodifiableSet` và hợp đồng view được backing bởi collection nguồn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html
- Java SE 26 — `List.copyOf`, unmodifiable list và snapshot cấu trúc: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html
- Java SE 26 — `Set.copyOf` và quy tắc phần tử trùng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html
- Java SE 26 — `Stream.collect`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
