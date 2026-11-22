# `Collection.removeIf()` và xóa theo điều kiện (Java 8+)

**`Collection.removeIf(Predicate)`** là API được bổ sung từ Java 8 để **xóa trực tiếp khỏi collection mọi phần tử thỏa một điều kiện**. Phương thức này giúp thay cho vòng lặp xóa thủ công dễ gây lỗi `ConcurrentModificationException`, đồng thời biểu đạt rõ ý định: "loại bỏ tất cả phần tử có đặc điểm X".

Khác với `Stream.filter(...)`, `removeIf(...)` **làm thay đổi collection gốc**. Nó không tạo danh sách kết quả mới và không trả về các phần tử bị xóa: giá trị trả về là `boolean` cho biết **có ít nhất một phần tử bị xóa hay không**.

Các hợp đồng trong bài vẫn được hỗ trợ trong những JDK hiện đại; ví dụ chạy chỉ dùng API có từ Java 8. Những lựa chọn xuất hiện từ Java 9/10/11/16 trở đi được ghi rõ phiên bản để tránh nhầm với Java 8.

## 1. Cú pháp và hành vi cốt lõi

Trong interface `java.util.Collection<E>`:

```java
default boolean removeIf(Predicate<? super E> filter)
```

- `E`: kiểu phần tử đang lưu trong collection.
- `Predicate<? super E>`: một hàm nhận phần tử và trả về `true` hoặc `false`.
- Nếu `filter.test(element)` trả `true`: phần tử đó **được xóa** khỏi collection.
- Nếu trả `false`: phần tử đó **được giữ lại**.
- Trả `true` nếu collection thay đổi vì đã xóa ít nhất một phần tử; trả `false` nếu không xóa phần tử nào.
- Nếu truyền chính `filter` là `null`, phương thức ném `NullPointerException`.
- Đây là một **optional operation**: một số collection không hỗ trợ xóa và có thể ném `UnsupportedOperationException`.

Ví dụ ngắn (đoạn mã giả định đã import `java.util.*`):

```java
List<Integer> numbers =
    new ArrayList<>(Arrays.asList(2, 3, 4, 5, 6, 7, 8));

boolean changed = numbers.removeIf(n -> n % 2 == 0);

System.out.println(changed); // true
System.out.println(numbers); // [3, 5, 7]
```

Lưu ý câu điều kiện **ngược với ý định giữ lại**: `n % 2 == 0` nghĩa là *xóa số chẵn*, nên các số lẻ ở lại. Nếu muốn giữ số chẵn thì viết `removeIf(n -> n % 2 != 0)`.

Một lần gọi khác không tìm thấy phần tử cần xóa:

```java
boolean removedNegatives = numbers.removeIf(n -> n < 0);
// false, numbers vẫn là [3, 5, 7].
```

Không nên dùng biến `changed` như số lượng phần tử bị xóa: nó chỉ là một cờ `boolean`. Nếu cần số lượng, có thể lấy chênh lệch `size()` trước/sau khi xóa **trong bối cảnh không có thay đổi đồng thời**, hoặc xây dựng logic báo cáo phù hợp.

## 2. `removeIf` khác gì `remove`, `removeAll`, `retainAll` và `filter`?

| API | Tiêu chí | Có thay đổi collection gốc? | Đặc điểm |
| --- | --- | --- | --- |
| `collection.remove(object)` | Một giá trị theo `equals` | Có | Xóa **một lần xuất hiện** phù hợp nếu collection cho phép trùng |
| `collection.removeIf(predicate)` | Điều kiện logic trên từng phần tử | **Có** | Xóa **mọi phần tử** được kiểm tra là thỏa điều kiện |
| `collection.removeAll(other)` | Phần tử thuộc một collection khác | Có | Xóa phần giao theo quy tắc membership |
| `collection.retainAll(other)` | Phần tử **không thuộc** collection khác | Có | Chỉ giữ lại các phần tử xuất hiện trong `other` |
| `collection.clear()` | Không có điều kiện | Có | Xóa toàn bộ nếu collection hỗ trợ |
| `stream.filter(predicate).collect(...)` | Điều kiện để **giữ** phần tử | **Không** sửa nguồn theo cách sử dụng đúng | Tạo một kết quả thu thập riêng, có thể thay đổi kiểu collection |

Ví dụ minh họa:

```java
List<String> a = new ArrayList<>(Arrays.asList("red", "blue", "red"));
a.remove("red");                  // [blue, red]
a.removeIf("red"::equals);        // [blue]
```

Điểm phân biệt: `remove("red")` chỉ loại một lần xuất hiện phù hợp trong `List`, còn `removeIf("red"::equals)` loại **toàn bộ** các lần xuất hiện "red" còn lại. Predicate `"red"::equals` cũng **an toàn khi gặp phần tử null** vì receiver là hằng chuỗi không-null.

Nếu mục tiêu là tạo danh sách mới mà vẫn giữ bản gốc:

```java
List<Integer> original =
    new ArrayList<>(Arrays.asList(1, 2, 3, 4, 5));

List<Integer> oddCopy = original.stream()
    .filter(n -> n % 2 != 0)
    .collect(Collectors.toList());

// original: [1, 2, 3, 4, 5]
// oddCopy:  [1, 3, 5]
```

`Collectors.toList()` có từ Java 8 nhưng **không cam kết** kiểu cài đặt và tính sửa được của danh sách trả về. Nếu muốn rõ là một `ArrayList` có thể chỉnh sửa, dùng `Collectors.toCollection(ArrayList::new)`. Từ Java 16 còn có `stream.toList()` (trả danh sách không chỉnh sửa được), nhưng đó **không phải API Java 8**.

**Quy tắc chọn:** dùng `removeIf` khi muốn sửa *chính collection hiện có* và được quyền sửa nó; dùng `filter` khi cần giữ nguyên nguồn, muốn một kết quả mới, hoặc đang xây dựng pipeline bất biến.

## 3. Cơ chế mặc định dựa trên `Iterator.remove()`

`removeIf` là **default method** của `Collection`. Tài liệu API mô tả cơ chế mặc định như sau:

1. Lấy `iterator()` của collection.
2. Duyệt từng phần tử còn lại bằng `Iterator.next()`.
3. Gọi `filter.test(element)`.
4. Nếu predicate trả `true`, gọi **`Iterator.remove()`** để xóa phần tử vừa duyệt.
5. Tiếp tục cho đến hết, trả `true` nếu có lần xóa nào thành công.

Có thể hình dung mã tương đương về **ý tưởng**:

```java
static <E> boolean removeMatching(Collection<E> c,
                                  Predicate<? super E> filter) {
    Objects.requireNonNull(filter);
    boolean changed = false;
    Iterator<E> it = c.iterator();
    while (it.hasNext()) {
        E item = it.next();
        if (filter.test(item)) {
            it.remove();
            changed = true;
        }
    }
    return changed;
}
```

Đây là **một hàm minh họa** chứ không phải mã cần viết trong ứng dụng để thay `removeIf`. Các implementation như `ArrayList` có thể **override** phương thức bằng thuật toán tối ưu hơn; không suy đoán độ phức tạp cụ thể của mọi loại collection chỉ từ bản default.

Nếu iterator **không hỗ trợ `remove()`** và có ít nhất một phần tử mà predicate muốn xóa, bản triển khai mặc định sẽ ném `UnsupportedOperationException` ở phần tử phù hợp đầu tiên. Một implementation cụ thể có thể tự override và có hành vi ném lỗi khác; vì vậy cần xét **hợp đồng của collection cụ thể**, không giả định mọi instance của `Collection` đều xóa được.

### Vì sao tránh xóa trực tiếp trong vòng `for-each`?

Đây là cách dễ gây lỗi khi duyệt `ArrayList`:

```java
List<Integer> values = new ArrayList<>(Arrays.asList(1, 2, 3, 4));

// KHÔNG nên làm: xóa cấu trúc list qua chính list khi iterator đang duyệt.
// for (Integer value : values) {
//     if (value % 2 == 0) values.remove(value);
// }
```

Vòng `for-each` thực chất sử dụng iterator. Sửa cấu trúc collection qua một đường khác khi đang duyệt có thể gây `ConcurrentModificationException` hoặc hành vi không mong muốn. Cơ chế **fail-fast** là khả năng phát hiện lỗi tốt nhất trong một số iterator, **không phải** biện pháp bảo đảm tính đúng hoặc an toàn đa luồng.

Hãy viết:

```java
values.removeIf(value -> value % 2 == 0);
// values = [1, 3]
```

Nếu thực sự cần thao tác chi tiết trong khi duyệt, có thể dùng `Iterator.remove()` đúng quy tắc, chỉ sau `next()` và tối đa một lần cho mỗi phần tử:

```java
Iterator<Integer> it = values.iterator();
while (it.hasNext()) {
    if (it.next() > 2) {
        it.remove();
    }
}
```

Đối với một điều kiện đơn giản, `removeIf` ngắn và biểu cảm hơn.

## 4. Viết predicate dễ đọc, đúng ý nghĩa và an toàn với `null`

### Kết hợp điều kiện bằng `&&` và `||`

Giả sử một tác vụ có các trường `status` và `priority`. Bạn muốn:

- Xóa mọi tác vụ có trạng thái `CANCELLED`.
- Hoặc xóa tác vụ `DONE` nhưng có độ ưu tiên nhỏ hơn 3.
- Giữ tác vụ `OPEN` và các tác vụ `DONE` có ưu tiên từ 3 trở lên.

Viết:

```java
tasks.removeIf(task ->
    "CANCELLED".equals(task.status)
        || ("DONE".equals(task.status) && task.priority < 3));
```

Đây là đoạn mã minh họa; lớp `Task` và danh sách `tasks` được khai báo đầy đủ ở mục 10. Dấu ngoặc làm rõ mức ưu tiên giữa `||` và `&&`, tránh xóa nhầm.

Có thể tách predicate thành tên nghiệp vụ dễ review:

```java
Predicate<Task> cancelled = t -> "CANCELLED".equals(t.status);
Predicate<Task> lowPriorityDone =
    t -> "DONE".equals(t.status) && t.priority < 3;

tasks.removeIf(cancelled.or(lowPriorityDone));
```

`Predicate.and(...)`, `Predicate.or(...)` và `Predicate.negate()` là API Java 8; chúng cho phép ghép quy tắc rõ ràng và **short-circuit** theo ngữ nghĩa logic.

### Xử lý phần tử `null`

Một số collection, ví dụ `ArrayList`, cho phép `null`. Câu lệnh sau không an toàn nếu có null:

```java
// Không an toàn nếu s == null:
// tokens.removeIf(s -> s.trim().isEmpty());
```

Cách đúng trong Java 8:

```java
List<String> tokens = new ArrayList<>(
    Arrays.asList("Java", null, "", "  ", "Stream"));

tokens.removeIf(s -> s == null || s.trim().isEmpty());
// [Java, Stream]
```

Nhờ `||` short-circuit, khi `s == null` là `true`, Java không gọi `s.trim()`. `String.trim().isEmpty()` là một cách xử lý đơn giản cho khoảng trắng cơ bản, nhưng không đồng nhất hoàn toàn với `String.isBlank()` (có từ Java 11) vì quy tắc nhận diện ký tự trắng khác nhau. Chọn kiểm tra phù hợp dữ liệu quốc tế hóa và target JDK.

### Predicate nên thuần và ổn định

Predicate lý tưởng chỉ **đọc phần tử và các dữ liệu bất biến cần thiết** rồi trả boolean; tránh:

- Gọi `collection.add/remove/clear` ngay trong predicate đang duyệt collection đó.
- Thay đổi các trường liên quan tới `equals/hashCode` của phần tử trong `HashSet` hoặc khóa trong `Map`.
- Truy cập trạng thái mutable được nhiều luồng cập nhật không có đồng bộ.
- Thực hiện gọi mạng, ghi cơ sở dữ liệu, gửi event hoặc log có side effect khó lặp lại trong logic lựa chọn phần tử.
- Dựa vào thứ tự gọi predicate khi collection vốn không cam kết thứ tự lặp.

Nếu predicate ném exception, exception được truyền lên caller. **Không có cam kết chung rằng `removeIf` sẽ rollback toàn bộ các lần xóa trước đó**, bởi cách xử lý phụ thuộc implementation; đừng coi `removeIf` là một giao dịch all-or-nothing của dữ liệu nghiệp vụ.

## 5. Hỗ trợ xóa tùy theo loại collection

| Collection / nguồn list | `removeIf` phù hợp? | Lưu ý |
| --- | --- | --- |
| `ArrayList` | Có | Cho phép xóa; giữ thứ tự tương đối của các phần tử còn lại |
| `LinkedList` | Có | Cho phép xóa; hiệu năng khác với `ArrayList` tùy loại thao tác |
| `HashSet` | Có | Loại phần tử theo predicate; thứ tự duyệt không được bảo đảm |
| `LinkedHashSet` | Có | Khi duyệt, giữ thứ tự chèn của các phần tử còn lại |
| `TreeSet` | Có | Duy trì thứ tự sắp xếp theo comparator sau khi xóa |
| `Arrays.asList(...)` | **Không cho xóa phần tử** | List có kích thước cố định; nếu có phần tử cần xóa sẽ ném `UnsupportedOperationException` |
| `Collections.unmodifiableList(...)` | **Không** | Là view không cho sửa; thao tác thay đổi bị từ chối |
| `List.of(...)` | **Không** | Danh sách không cho sửa, có từ Java 9; không chấp nhận phần tử `null` |
| `List.copyOf(...)` | **Không** | Có từ Java 10; bản sao không cho sửa và không chấp nhận null |
| `CopyOnWriteArrayList` | Có, theo override | Phù hợp môi trường nhiều thao tác đọc hơn ghi; cập nhật tạo chi phí sao chép |
| `Map.entrySet()/keySet()/values()` | Tùy map/view | Đây là `Collection` view; xóa trên view được hỗ trợ có thể xóa **entry khỏi map gốc** |

`Collection` là một abstraction có nhiều implementation; **không được suy ra tính sửa được chỉ từ kiểu biến `List`, `Set` hay `Collection`**.

### `Arrays.asList`: list cố định kích thước

```java
List<Integer> fixedSize = Arrays.asList(1, 2, 3);

// Có phần tử phù hợp nhưng list không hỗ trợ xóa:
// fixedSize.removeIf(n -> n == 2); // UnsupportedOperationException
```

`Arrays.asList` cho phép thay thế một phần tử qua `set(index, value)` nhưng **không thay đổi số phần tử** bằng `add` hoặc `remove`. Nếu muốn xóa, sao chép:

```java
List<Integer> editable = new ArrayList<>(Arrays.asList(1, 2, 3));
editable.removeIf(n -> n == 2);
// [1, 3]
```

Đừng dựa vào việc `removeIf` có nhất thiết ném exception khi **không có phần tử nào phù hợp** hay không: implementation không hỗ trợ thay đổi có thể xử lý trường hợp này khác nhau. Điều cần nhớ là nó **không phải nguồn để thực hiện xóa thực sự**.

### Danh sách không cho sửa

`Collections.unmodifiableList(source)` (có từ trước Java 8 và vẫn được hỗ trợ) tạo một **view không cho thay đổi qua view đó**. Phương thức `removeIf` sẽ bị từ chối. Nếu `source` phía dưới vẫn còn được tham chiếu và bị sửa qua đường khác, nội dung nhìn từ view có thể thay đổi; "unmodifiable view" **không đồng nghĩa dữ liệu đã được snapshot hoặc deep immutable**.

Java 9+ có `List.of(...)`; Java 10+ có `List.copyOf(...)`. Chúng đều không hỗ trợ xóa, nhưng là những API bổ sung trong các phiên bản hiện đại, không thuộc Java 8 gốc. Với danh sách có thể sửa, chuyển rõ ràng sang `new ArrayList<>(readOnly)` nếu muốn tạo bản sao độc lập trước khi xóa.

### `CopyOnWriteArrayList` trong môi trường đa luồng

`CopyOnWriteArrayList` có cách quản lý snapshot cho iterator, và các thao tác chỉnh sửa như `removeIf` được implementation hỗ trợ theo chính sách của nó. Vì cần sao chép dữ liệu khi cập nhật, cấu trúc này **không nên được chọn chỉ để xóa hàng loạt thường xuyên** trên danh sách rất lớn. Nó phù hợp hơn khi lượng đọc nhiều, lượng thay đổi ít.

`CopyOnWriteArrayList` có `Iterator` không hỗ trợ `Iterator.remove()`, nhưng **bản thân collection override `removeIf`**, vì vậy không nên suy luận rằng mọi collection có iterator không thể remove đều chắc chắn không hỗ trợ `removeIf`. Chỉ có *default implementation* phụ thuộc trực tiếp vào `Iterator.remove()`.

## 6. Xóa theo điều kiện trong `Set` và `Map`

### `Set`

`Set` kế thừa `Collection.removeIf`. Ví dụ:

```java
Set<String> tags = new LinkedHashSet<>(
    Arrays.asList("java", "old", "stream", "archived"));

tags.removeIf(tag -> tag.equals("old") || tag.startsWith("a"));
// [java, stream]
```

Nếu thay `LinkedHashSet` bằng `HashSet`, kết quả vẫn chỉ chứa hai phần tử "java" và "stream", nhưng **thứ tự lặp không được cam kết**. Nếu thay bằng `TreeSet`, set luôn tuân thủ thứ tự comparator.

Không dùng `removeIf` như một cách "sửa" thông tin trong một đối tượng đang làm khóa trong hash-based collection; việc thay đổi các trường quyết định `equals/hashCode` khi phần tử vẫn nằm trong set có thể làm cấu trúc không nhất quán.

### `Map`: thao tác trên view

Interface `Map` **không mở rộng `Collection`**, nên bạn không gọi `map.removeIf(...)` trực tiếp. Thay vào đó, `entrySet()`, `keySet()` và `values()` trả về các view thuộc họ `Collection` mà ở các map có khả năng sửa, việc xóa phần tử trên view sẽ loại **mapping** tương ứng khỏi map.

Ví dụ xóa mọi entry có giá trị nhỏ hơn 3:

```java
Map<String, Integer> counts = new LinkedHashMap<>();
counts.put("java", 5);
counts.put("old", 1);
counts.put("stream", 4);

counts.entrySet().removeIf(entry -> entry.getValue() < 3);
// {java=5, stream=4}
```

Những hướng khác:

```java
counts.keySet().removeIf(key -> key.startsWith("tmp-"));
counts.values().removeIf(value -> value == 0);
```

Các đoạn này giả định `counts` là một map có view hỗ trợ xóa (như `LinkedHashMap` trong ví dụ). `keySet()` chọn theo **khóa**, `values()` chọn theo **giá trị**, `entrySet()` thấy đồng thời cả khóa lẫn giá trị. Đối với một map không cho sửa hoặc view có ràng buộc khác, có thể gặp `UnsupportedOperationException`.

Khi điều kiện vừa phụ thuộc khóa vừa phụ thuộc giá trị, `entrySet().removeIf(...)` thường dễ đọc hơn việc tự lặp `keySet()` rồi gọi `map.remove(key)`.

## 7. Xóa trong `subList`: thay đổi cả danh sách cha

`List.subList(fromIndex, toIndex)` thông thường trả về **view** của một đoạn danh sách, không phải bản sao dữ liệu độc lập. Vì vậy:

```java
List<Integer> parent =
    new ArrayList<>(Arrays.asList(0, 1, 2, 3, 4, 5));

parent.subList(1, 5).removeIf(n -> n % 2 == 0);
// parent = [0, 1, 3, 5]
```

Phần `subList(1,5)` ban đầu là `[1,2,3,4]`; `removeIf` xóa 2 và 4 khỏi chính danh sách cha. Cấu trúc view/parent của từng implementation cần được tôn trọng. Với `ArrayList`, sửa cấu trúc list cha theo đường khác khi còn sử dụng subList cũ có thể khiến thao tác trên view không còn hợp lệ.

Nếu muốn xóa mà **không** đụng tới `parent`:

```java
List<Integer> part = new ArrayList<>(parent.subList(1, 3));
part.removeIf(n -> n > 1);
```

Lúc này `part` là danh sách độc lập; việc xóa trên `part` không xóa phần tử khỏi `parent`.

## 8. Ngoại lệ, thứ tự và giới hạn nguyên tử

### Các ngoại lệ thường cần biết

| Tình huống | Biểu hiện có thể gặp |
| --- | --- |
| Truyền `null` làm `Predicate` | `NullPointerException` |
| Phần tử null nhưng predicate gọi method trên phần tử | `NullPointerException` ngay trong predicate |
| Collection/view không hỗ trợ xóa và có yêu cầu xóa | `UnsupportedOperationException` |
| Predicate tự ném `RuntimeException` | Exception được chuyển tới caller |
| Mã khác sửa `ArrayList` thiếu đồng bộ khi đang duyệt | Có thể có `ConcurrentModificationException` hoặc hành vi không xác định được để dựa vào |
| Predicate tự sửa cùng collection đang xử lý | Vi phạm giả định duyệt ổn định; có thể gặp lỗi hoặc kết quả không mong muốn |

**Điểm cốt lõi:** `removeIf` là một thao tác cập nhật collection **trong bộ nhớ**, không phải giao dịch cơ sở dữ liệu. Nó không tự gọi `DELETE` vào database, không đồng bộ ra hệ thống lưu trữ và không hứa rollback khi predicate hoặc quá trình duyệt thất bại. Nếu dữ liệu nghiệp vụ đòi **all-or-nothing**, cần thiết kế giao dịch hoặc tạo kết quả mới và chỉ thay tham chiếu sau khi đã kiểm chứng.

### Thứ tự phần tử còn lại

Với `List` duy trì encounter order, `removeIf` không phải thao tác sort. Nó **giữ thứ tự tương đối của các phần tử không bị xóa**. Ví dụ:

```java
List<String> stages = new ArrayList<>(
    Arrays.asList("NEW", "DONE", "RUNNING", "DONE", "FAILED"));

stages.removeIf("DONE"::equals);
// [NEW, RUNNING, FAILED]
```

`HashSet` không cam kết thứ tự lặp, nhưng `removeIf` cũng không thể được dùng để thiết lập một thứ tự cụ thể cho set đó.

## 9. Lưu ý về hiệu năng và đa luồng

### Hiệu năng tùy implementation

- `ArrayList` có cơ chế loại bỏ hàng loạt được tối ưu trong các JDK thông dụng; nhiều phần tử cùng được lọc trong một lượt, thích hợp với nhu cầu xóa tại chỗ.
- `LinkedList` dùng cấu trúc liên kết; xóa qua iterator có đặc tính khác với xóa theo chỉ số của array-based list.
- `HashSet` và `LinkedHashSet` không phải array-based list và có chi phí theo cấu trúc hash; thứ tự không phải lợi thế của `HashSet`.
- Bản `Collection.removeIf` mặc định dựa vào `Iterator.remove()`; nếu implementation xóa từng phần tử đắt đỏ, tổng thời gian có thể khác biệt lớn so với `ArrayList`.
- `CopyOnWriteArrayList` trả giá cho việc tạo bản sao khi sửa; phù hợp workload đọc nhiều hơn ghi.

Không khẳng định mọi collection đều có `removeIf` chạy `O(n)` với cùng hệ số hoặc không cấp phát bộ nhớ. Khi dữ liệu lớn, hãy đo với loại collection và tỉ lệ phần tử bị xóa thực tế.

### An toàn đa luồng

`ArrayList.removeIf` **không tự động an toàn nếu các luồng khác đồng thời sửa/duyệt cùng list**. Một phương thức có tên `removeIf` không làm mất yêu cầu đồng bộ của loại collection. Đồng thời, gọi `parallelStream().forEach(list::remove)` không tương đương `removeIf` và có thể làm sai cấu trúc dữ liệu nếu thiếu đồng bộ.

Nếu nhiều luồng cần cùng cập nhật, hãy lựa chọn cấu trúc concurrent phù hợp với **kiểu thao tác thực sự cần**, xác định chính sách nhất quán, và bảo vệ cả các chuỗi thao tác nhiều bước. `CopyOnWriteArrayList` là một lựa chọn cho danh sách được đọc thường xuyên và cập nhật hiếm; không mặc định nó tối ưu cho các lượt xóa hàng loạt tần suất cao.

Các predicate mang trạng thái có thể thay đổi do luồng khác cũng khó kiểm tra và tái hiện. Với tác vụ xóa theo quy tắc nghiệp vụ, nên chốt điều kiện/snapshot đầu vào cần thiết hoặc đồng bộ ở phạm vi phù hợp trước khi gọi.

## 10. Chương trình Java hoàn chỉnh, có thể chạy

Tạo file **`CollectionRemoveIfDemo.java`**. Chương trình dùng API Java 8, chạy trên JDK 17+; những trường hợp không cho xóa được bắt ngoại lệ và in thông báo ổn định để quan sát hành vi.

```java
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;

public class CollectionRemoveIfDemo {
    static final class Task {
        final int id;
        final String status;
        final int priority;

        Task(int id, String status, int priority) {
            this.id = id;
            this.status = status;
            this.priority = priority;
        }

        @Override
        public String toString() {
            return id + ":" + status + ":" + priority;
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(
                Arrays.asList(2, 3, 4, 5, 6, 7, 8));
        boolean changed = numbers.removeIf(n -> n % 2 == 0);
        boolean changedAgain = numbers.removeIf(n -> n < 0);
        System.out.println("removed evens: " + changed + " -> " + numbers);
        System.out.println("removed negatives: " + changedAgain);

        List<String> tokens = new ArrayList<>(
                Arrays.asList("Java", null, "", "  ", "Stream"));
        tokens.removeIf(s -> s == null || s.trim().isEmpty());
        System.out.println("clean tokens: " + tokens);

        List<Task> tasks = new ArrayList<>(Arrays.asList(
                new Task(101, "DONE", 2),
                new Task(102, "OPEN", 4),
                new Task(103, "CANCELLED", 1),
                new Task(104, "DONE", 5)));
        tasks.removeIf(t -> "CANCELLED".equals(t.status)
                || ("DONE".equals(t.status) && t.priority < 3));
        System.out.println("active tasks: " + tasks);

        Set<String> tags = new LinkedHashSet<>(
                Arrays.asList("java", "old", "stream", "archived"));
        tags.removeIf(tag -> tag.equals("old") || tag.startsWith("a"));
        System.out.println("tags: " + tags);

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("java", 5);
        counts.put("old", 1);
        counts.put("stream", 4);
        counts.entrySet().removeIf(e -> e.getValue() < 3);
        System.out.println("map: " + counts);

        List<Integer> original = new ArrayList<>(
                Arrays.asList(1, 2, 3, 4, 5));
        List<Integer> oddCopy = original.stream()
                .filter(n -> n % 2 != 0)
                .collect(Collectors.toList());
        System.out.println("filter original: " + original);
        System.out.println("filter result: " + oddCopy);

        List<Integer> fixedSize = Arrays.asList(1, 2, 3);
        try {
            fixedSize.removeIf(n -> n == 2);
        } catch (UnsupportedOperationException ex) {
            System.out.println("fixed-size: UnsupportedOperationException");
        }

        List<Integer> readOnly = Collections.unmodifiableList(
                new ArrayList<>(Arrays.asList(1, 2, 3)));
        try {
            readOnly.removeIf(n -> n == 2);
        } catch (UnsupportedOperationException ex) {
            System.out.println("read-only: UnsupportedOperationException");
        }

        CopyOnWriteArrayList<Integer> cow =
                new CopyOnWriteArrayList<>(Arrays.asList(1, 2, 3, 4));
        cow.removeIf(n -> n > 2);
        System.out.println("copy-on-write: " + cow);

        List<Integer> parent = new ArrayList<>(
                Arrays.asList(0, 1, 2, 3, 4, 5));
        parent.subList(1, 5).removeIf(n -> n % 2 == 0);
        System.out.println("subList parent: " + parent);
    }
}
```

Lệnh chạy (JDK 17+):

```bash
javac -encoding UTF-8 CollectionRemoveIfDemo.java
java CollectionRemoveIfDemo
```

**Kết quả chuẩn:**

```text
removed evens: true -> [3, 5, 7]
removed negatives: false
clean tokens: [Java, Stream]
active tasks: [102:OPEN:4, 104:DONE:5]
tags: [java, stream]
map: {java=5, stream=4}
filter original: [1, 2, 3, 4, 5]
filter result: [1, 3, 5]
fixed-size: UnsupportedOperationException
read-only: UnsupportedOperationException
copy-on-write: [1, 2]
subList parent: [0, 1, 3, 5]
```

**Giải thích từng kết quả:**

1. Các số chẵn 2,4,6,8 bị xóa khỏi `numbers`, nên còn 3,5,7; lần thứ hai không có số âm nên trả `false`.
2. `tokens` loại null, chuỗi rỗng và chuỗi gồm khoảng trắng cơ bản mà không bị `NullPointerException`.
3. Tác vụ 101 bị xóa vì `DONE` và ưu tiên 2; tác vụ 103 bị xóa vì `CANCELLED`. Tác vụ 104 vẫn giữ vì `DONE` nhưng ưu tiên 5.
4. `LinkedHashSet` loại hai thẻ "old" và "archived", còn thứ tự chèn của "java" và "stream".
5. `counts.entrySet().removeIf(...)` xóa mapping `old=1` khỏi map gốc, giữ hai mapping còn lại.
6. `Stream.filter` tạo `oddCopy`, không sửa `original`.
7. `Arrays.asList` và `Collections.unmodifiableList` minh họa hai lý do **không hỗ trợ xóa** khác nhau.
8. `CopyOnWriteArrayList` hỗ trợ `removeIf` qua implementation của nó, dù iterator snapshot không có phép `remove()`.
9. `subList` là một view của `parent`; xóa 2,4 trong vùng nhìn thấy cũng làm danh sách cha còn `[0,1,3,5]`.

Mọi ví dụ có đầu ra phụ thuộc thứ tự đều dùng `List`, `LinkedHashSet` hoặc `LinkedHashMap` để tránh dựa vào thứ tự duyệt không cam kết của `HashSet`/`HashMap`.

## 11. Những lỗi thường gặp và cách xử lý

| Sai lầm | Vì sao có thể sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `removeIf(p)` **giữ** phần tử khi `p == true` | Nhầm với `Stream.filter` | Nhớ `true` = **xóa** |
| Dùng `remove(object)` nhưng muốn loại mọi lần xuất hiện | `List.remove(Object)` chỉ xóa một lần phù hợp | Dùng `removeIf(x -> Objects.equals(x, value))` |
| Xóa bằng `list.remove(x)` trong `for-each` | Sửa cấu trúc list ngoài iterator đang duyệt | Dùng `removeIf` hoặc `Iterator.remove` đúng quy tắc |
| Cho rằng mọi `List` đều có thể thay đổi kích thước | `Arrays.asList` cố định kích thước, nhiều list không cho sửa | Tạo `new ArrayList<>(source)` khi cần bản sao có thể sửa |
| Gọi method trên phần tử có thể `null` | Predicate ném `NullPointerException` | Kiểm tra `x == null` trước hoặc dùng mẫu null-safe |
| Cho rằng `removeIf` trả số phần tử đã xóa | Trả `boolean` | Tính chênh lệch size trong điều kiện không có thay đổi đồng thời |
| Đặt thao tác thêm/xóa collection trong predicate | Dễ phá iterator hoặc gây trạng thái khó đoán | Predicate nên chỉ đánh giá điều kiện |
| Dùng `stream.filter` rồi nghĩ list gốc thay đổi | `filter` chỉ tạo pipeline, bản thân không sửa list nguồn | Dùng `removeIf` nếu yêu cầu cập nhật tại chỗ |
| Gọi `map.removeIf` | `Map` không kế thừa `Collection` | Dùng `entrySet()/keySet()/values().removeIf` theo nhu cầu |
| Coi `Collections.unmodifiableList` là snapshot | Đây là view, thay đổi qua backing list có thể vẫn hiện ra | Sao chép hoặc sử dụng API bất biến phù hợp |
| Nghĩ `removeIf` tự rollback nếu predicate ném lỗi | API không cam kết atomic rollback chung | Tách bước kiểm tra và cập nhật có kiểm soát nếu cần giao dịch |
| Nghĩ `removeIf` tự thread-safe vì Java 8 có lambda | Thread-safety phụ thuộc collection và cách dùng | Chọn collection đồng thời/phạm vi khóa thích hợp |
| Dùng `CopyOnWriteArrayList` cho dữ liệu rất lớn, sửa liên tục | Copy-on-write tăng chi phí cập nhật | Chọn cấu trúc dựa trên tỉ lệ đọc/ghi thực tế |
| Giả định `List.of` hoặc `String.isBlank` có trong Java 8 | Chúng bắt đầu từ Java 9 và Java 11 | Dùng API phù hợp target JDK; ghi rõ phiên bản |
| Xóa bằng `subList.removeIf` rồi ngạc nhiên vì list cha thay đổi | `subList` thường là view, không phải bản sao | Tạo `new ArrayList<>(subList)` nếu muốn độc lập |

## 12. Bài tập tự kiểm tra

### Bài 1 — Xóa theo khoảng giá trị

Cho:

```java
List<Integer> scores =
    new ArrayList<>(Arrays.asList(4, 7, 10, 12, 15, 20));
```

Yêu cầu: loại phần tử `x < 10` hoặc `x > 15`.

**Đáp án:**

```java
scores.removeIf(x -> x < 10 || x > 15);
// [10, 12, 15]
```

### Bài 2 — Giữ lại các tên hợp lệ

Cho:

```java
List<String> names =
    new ArrayList<>(Arrays.asList("An", null, " ", "Binh", ""));
```

Hãy loại tên null và tên trống/chỉ gồm khoảng trắng cơ bản, dùng cú pháp Java 8.

**Đáp án:**

```java
names.removeIf(s -> s == null || s.trim().isEmpty());
// [An, Binh]
```

### Bài 3 — Chọn in-place hay tạo bản sao

Một service nhận danh sách đơn hàng từ hàm gọi; hợp đồng service **không được làm thay đổi danh sách của caller**. Bạn nên dùng `orders.removeIf(...)` không?

**Đáp án:** Không nên trực tiếp sửa đối tượng của caller. Chọn `orders.stream().filter(keepCondition).collect(...)` hoặc tạo `new ArrayList<>(orders)` rồi mới gọi `removeIf`. Quyết định phải dựa vào hợp đồng ownership và mutability, không phải chỉ theo độ ngắn của câu lệnh.

### Bài 4 — Xóa mapping khỏi map

Cho một `Map<String,Integer>` lưu số lần xuất hiện. Hãy xóa mọi mapping có giá trị bằng 0 mà không tự tạo iterator để gọi `map.remove(key)`.

**Đáp án:**

```java
counts.entrySet().removeIf(entry -> entry.getValue() == 0);
```

Giả định `counts` là một map có khả năng sửa và các giá trị khác null. Nếu giá trị có thể null, phải xác định rõ chính sách và viết predicate tương ứng.

### Bài 5 — Exception giữa chừng

Một predicate xử lý được ba phần tử rồi ném `IllegalArgumentException` ở phần tử thứ tư. Có thể khẳng định collection chắc chắn giữ nguyên toàn bộ dữ liệu không?

**Đáp án:** Không. `removeIf` không có hợp đồng chung về rollback. Cách triển khai và thời điểm xóa cụ thể có thể khác giữa các collection; nghiệp vụ cần giao dịch phải được thiết kế riêng.

### Bài 6 — Fixed-size list

Vì sao đoạn sau không phải một cách hợp lệ để xóa giá trị 2?

```java
List<Integer> values = Arrays.asList(1, 2, 3);
// values.removeIf(x -> x == 2);
```

**Đáp án:** `Arrays.asList` tạo một list cố định kích thước, không hỗ trợ phép remove thực sự. Cần sao chép sang `ArrayList` có thể sửa trước khi xóa, hoặc dùng `Stream.filter` để tạo danh sách kết quả mới.

## 13. Checklist khi dùng `removeIf` trong dự án thực tế

- [ ] Có thật sự muốn sửa **chính collection gốc**, hay cần giữ nguồn và tạo kết quả mới?
- [ ] Collection hiện tại có hỗ trợ xóa không? Có phải `Arrays.asList`, view không cho sửa, hay một collection tùy biến?
- [ ] Predicate trả `true` đúng cho **phần tử cần loại**?
- [ ] Predicate có an toàn với `null` và các trường nullable?
- [ ] Predicate có side effect làm thay đổi collection đang duyệt hay không?
- [ ] Khi xóa qua `subList` hoặc `Map` view, đã chấp nhận ảnh hưởng lên cấu trúc gốc chưa?
- [ ] Có yêu cầu về số lượng phần tử xóa, báo cáo audit hoặc khôi phục? `boolean` có đủ không?
- [ ] Exception trong predicate có gây trạng thái nghiệp vụ cần rollback hoặc khôi phục không?
- [ ] Có luồng khác đồng thời đọc/sửa dữ liệu và cần biện pháp đồng bộ không?
- [ ] Có đang áp dụng đúng các API khả dụng cho phiên bản JDK đang triển khai?
- [ ] Có test đủ: danh sách rỗng, không có phần tử khớp, tất cả phần tử khớp, phần tử trùng, giá trị null, collection không sửa được?

**Ghi nhớ:** `Collection.removeIf(predicate)` là một cách ngắn, hiện đại và vẫn được hỗ trợ để **xóa có điều kiện tại chỗ**. Dùng khi collection cho phép sửa, predicate rõ ràng và môi trường truy cập được kiểm soát; dùng `Stream.filter` khi cần tạo kết quả mới và giữ nguyên nguồn.

### Tài liệu API chính thức, còn áp dụng

- [`Collection.removeIf` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html): chữ ký, optional operation, bản default dùng `Iterator.remove`, giá trị trả về và ngoại lệ.
- [`Predicate` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Predicate.html): `test`, `and`, `or` và `negate`.
- [`ArrayList` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayList.html): hành vi của mutable list.
- [`Collections.unmodifiableList` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html): view không cho sửa.
- [`CopyOnWriteArrayList` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): chính sách đọc snapshot và cập nhật copy-on-write.
- [`Stream.filter` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): lựa chọn giữ phần tử để tạo kết quả mới.