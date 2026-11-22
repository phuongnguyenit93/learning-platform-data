# `Collectors.toUnmodifiableSet` và tính không có thứ tự (Java 10+)

## 1. Vấn đề cốt lõi

Khi một luồng dữ liệu (*Stream*) chứa các phần tử, `Collectors.toUnmodifiableSet()` gom chúng thành **một `Set` không cho sửa đổi**, loại bỏ các phần tử trùng nhau theo quan hệ `equals`. Collector này xuất hiện từ **Java 10** và vẫn là API hiện hành trong Java hiện đại.

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Binh", "An", "Chi");
Set<String> uniqueNames =
        names.stream().collect(Collectors.toUnmodifiableSet());

// uniqueNames.size() == 3
// uniqueNames chứa An, Binh, Chi; không hứa thứ tự duyệt.
```

Đây là các lệnh minh họa cần đặt trong một phương thức Java thích hợp. Những điều cần nhớ đồng thời:

1. **Không sửa được kết quả:** không thể thêm, xóa hoặc thay phần tử qua `Set` trả về.
2. **Không có phần tử `null`:** collector từ chối `null` bằng `NullPointerException`.
3. **Tự loại trùng theo `equals`:** mỗi nhóm phần tử được coi là bằng nhau chỉ đóng góp tối đa một phần tử.
4. **Không có bảo đảm về thứ tự:** collector được đặc tả là **`UNORDERED`** và kết quả không cam kết thứ tự khi duyệt hay in ra.

**“Unordered” không có nghĩa “random mỗi lần gọi”, cũng không có nghĩa dữ liệu bị thất lạc.** Nó có nghĩa chương trình **không được dựa vào một thứ tự cụ thể** như thứ tự đầu vào, thứ tự chèn, thứ tự tự nhiên hoặc thứ tự thấy trên một bản JDK.

## 2. Cách dùng với Stream

Chữ ký của factory collector:

```java
public static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()
```

Đây là **chữ ký trong API `java.util.stream.Collectors`**, không phải phương thức do ứng dụng tự viết. Phương thức `collect` dùng collector để tích lũy các phần tử trong pipeline:

```java
var result = List.of(3, 1, 2, 3, 2)
        .stream()
        .collect(Collectors.toUnmodifiableSet());

// Kiểu tĩnh của result: Set<Integer>
// Các phần tử theo giá trị: 1, 2, 3
```

Nếu muốn lọc/chuyển đổi trước khi gom:

```java
var tokens = List.of("  JAVA  ", "API", "java", "stream");

var normalized = tokens.stream()
        .map(String::trim)
        .map(String::toLowerCase)
        .collect(Collectors.toUnmodifiableSet());

// Các giá trị: "java", "api", "stream"
// Không giả định chúng sẽ được duyệt theo thứ tự xuất hiện.
```

Trong pipeline này, bước `map` xác định nội dung đầu ra; collector đảm nhận việc loại trùng và tạo kết quả không sửa được. Việc sử dụng `var` chỉ suy luận kiểu `Set<String>` của biểu thức và **không thay đổi** hợp đồng của collector.

## 3. `UNORDERED` thực sự có nghĩa gì?

Tài liệu Javadoc ghi rõ `Collectors.toUnmodifiableSet()` là một **unordered collector**. Có thể kiểm tra characteristic của collector:

```java
import java.util.stream.Collector;
import java.util.stream.Collectors;

boolean unordered = Collectors.toUnmodifiableSet()
        .characteristics()
        .contains(Collector.Characteristics.UNORDERED);
// unordered == true
```

Các dòng trên minh họa mã trong một phương thức.

Phân biệt ba khái niệm:

- **Encounter order của nguồn:** một `List` đưa vào `stream()` có thứ tự phần tử theo danh sách, còn nhiều nguồn dữ liệu khác không bảo đảm encounter order.
- **Characteristic `UNORDERED` của collector:** kết quả của phép gom không bị ràng buộc bởi một thứ tự encounter cố định. Collector có thể xử lý và kết hợp các phần tử mà không phải bảo toàn thứ tự đầu vào.
- **Iteration order của Set kết quả:** thứ tự mà `iterator()`, vòng `for` hoặc `toString()` thể hiện. `toUnmodifiableSet` **không cam kết** thứ tự này.

Do đó, ngay cả khi nguồn được sắp xếp:

```java
var set = List.of("c", "a", "b")
        .stream()
        .sorted()
        .collect(Collectors.toUnmodifiableSet());

// Không được khẳng định set in thành [a, b, c].
```

Bước `sorted()` chỉ làm các phần tử stream đi qua một thứ tự sắp xếp trong giai đoạn pipeline. Bước cuối thu thành một `Set` không có thứ tự được bảo đảm, nên không thể dùng `sorted()` để thiết lập iteration order lâu dài cho kết quả.

**Lưu ý:** `UNORDERED` **không đồng nghĩa với** `CONCURRENT`, không phải lời hứa collector xử lý dữ liệu song song, và không phải một yêu cầu phải gọi `parallelStream()`. Đó là thông tin đặc tính của collector về ràng buộc thứ tự kết quả.

## 4. Vì sao không nên in trực tiếp Set để so sánh output?

Ví dụ:

```java
var set = List.of("b", "a", "c")
        .stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(set);
```

Dù set chứa đúng ba giá trị, **không thể cam kết chuỗi in ra** sẽ là `[a, b, c]`, `[b, a, c]` hay một hoán vị nào khác. Tài liệu Java Core Libraries còn mô tả khả năng thứ tự duyệt được *randomize* giữa những lần chạy JVM đối với các tập tạo bởi những factory không sửa được.

Nếu cần **in ra có thứ tự xác định để kiểm thử hoặc tạo báo cáo**, hãy sắp xếp **tại thời điểm xuất**:

```java
var result = List.of("b", "a", "c")
        .stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(new java.util.TreeSet<>(result));
// [a, b, c] với String theo thứ tự tự nhiên
```

`TreeSet` ở đây chỉ được dùng để **hiển thị theo thứ tự**, không làm collector gốc trở thành ordered. Với kiểu phần tử không có natural ordering, cần cung cấp một `Comparator` phù hợp hoặc sắp xếp một `List` riêng khi hiển thị.

Trong unit test:

- **Nên:** `assertEquals(Set.of("a", "b"), result)`, vì `Set.equals` so sánh **thành viên**.
- **Không nên:** `assertEquals("[a, b]", result.toString())`, vì `toString()` phụ thuộc iteration order không được bảo đảm.

## 5. Loại trùng: giữ một phần tử bất kỳ trong nhóm bằng nhau

`Set` không chứa hai phần tử được coi là trùng nhau theo `equals`. Javadoc `Collectors.toUnmodifiableSet` nói rõ: nếu đầu vào có phần tử trùng, collector có quyền giữ **một phần tử bất kỳ** trong nhóm trùng đó.

Với giá trị bất biến phổ biến:

```java
var result = List.of("A", "B", "A", "C")
        .stream()
        .collect(Collectors.toUnmodifiableSet());

// result.size() == 3
// result.contains("A"), "B", "C" đều true
```

Với `String`, giữ một trong hai giá trị bằng `"A"` không thay đổi nội dung theo `equals`. Nhưng nếu đối tượng nghiệp vụ có:

- `equals` và `hashCode` dựa trên `id`;
- trong khi một thuộc tính khác như `displayName` khác nhau giữa hai instance có cùng `id`,

thì **không được dựa vào collector để chọn bản ghi đến trước, đến sau, hay có dữ liệu mới nhất**. Kết quả có thể giữ một đại diện bất kỳ của nhóm tương đương. Nếu nghiệp vụ cần ưu tiên bản ghi mới nhất hoặc đầu tiên, phải thiết kế một bước chọn/merge rõ ràng, ví dụ gom theo key với merger có chủ ý trước khi tạo tập kết quả.

**Quan trọng:** không đồng nhất kết quả của `toUnmodifiableSet` với `Set.of(...)` về cách xử lý trùng:

```java
var collected = List.of("A", "A")
        .stream()
        .collect(Collectors.toUnmodifiableSet()); // hợp lệ, 1 phần tử

var copied = Set.copyOf(List.of("A", "A")); // hợp lệ, 1 phần tử

// var direct = Set.of("A", "A"); // IllegalArgumentException khi chạy
```

`Set.of` nhận các đối số trùng nhau sẽ ném `IllegalArgumentException`. Còn `toUnmodifiableSet` và `Set.copyOf` xử lý trùng theo hợp đồng riêng của chúng bằng cách giữ một phần tử đại diện.

## 6. Quy tắc với `null`: không lọc tự động

Factory `toUnmodifiableSet` **không cho phép phần tử `null`**. Nó ném `NullPointerException` nếu stream đưa `null` tới collector:

```java
var values = java.util.Arrays.asList("A", null, "B");

// Lệnh sau sẽ ném NullPointerException khi collect:
// var result = values.stream().collect(Collectors.toUnmodifiableSet());
```

Một cách xử lý khi nghiệp vụ cho phép **bỏ các giá trị null**:

```java
var safe = java.util.Arrays.asList("A", null, "B")
        .stream()
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());

// safe chứa "A" và "B", không có null
```

Tuy nhiên, việc bỏ `null` phải là **quyết định nghiệp vụ**, không nên làm chỉ để né ngoại lệ nếu dữ liệu có ý nghĩa khi mang giá trị `null`. Nếu cần lưu `null`, phải chọn một cấu trúc và hợp đồng khác (và cân nhắc tại sao `null` là một phần tử hợp lệ).

`Collectors.toSet()` không phải sự thay thế tương đương để đảm bảo mọi `null` được chấp nhận. Javadoc của `toSet` không bảo đảm implementation, tính sửa được hoặc các thuộc tính liên quan. Nếu ứng dụng cần một `Set` cụ thể với hợp đồng về `null`, hãy chỉ định implementation phù hợp.

## 7. So sánh các collector và các cách tạo Set khác

| Cách viết | Kết quả chính | Có bảo đảm thứ tự duyệt? | Có bảo đảm không sửa? |
| --- | --- | --- | --- |
| `stream.collect(Collectors.toUnmodifiableSet())` | Set loại trùng, cấm `null` | **Không; UNORDERED** | **Có** |
| `stream.collect(Collectors.toSet())` | Set loại trùng, loại cụ thể không được bảo đảm | **Không; UNORDERED** | **Không có bảo đảm** |
| `stream.collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet` loại trùng | **Giữ thứ tự chèn**; với nguồn ordered tuần tự, phản ánh encounter order | **Không**, kết quả sửa được |
| `stream.collect(Collectors.toUnmodifiableList())` | List giữ cả phần tử trùng | **Có**, theo encounter order của nguồn nếu có | **Có** |
| `Set.copyOf(collection)` | Set không sửa, loại trùng, cấm `null` | **Không** | **Có** |
| `Set.of("A", "B")` | Set không sửa, cấm `null`, **từ chối đối số trùng** | **Không** | **Có** |

**Đặc biệt về `toSet()`:** dù một JDK cụ thể thường trả về loại Set có thể sửa, chương trình đúng không nên phụ thuộc vào điều này vì tài liệu API không cam kết loại cụ thể hoặc khả năng sửa của kết quả. Dùng `toUnmodifiableSet()` khi mục tiêu là **một Set không thể sửa**, không phải dựa vào hành vi hiện tại của `toSet()`.

## 8. Nếu cần thứ tự, chọn hợp đồng khác

### 8.1. Cần duy nhất và giữ encounter order

Nếu muốn loại trùng **nhưng vẫn giữ thứ tự xuất hiện lần đầu**, với một stream ordered tuần tự bạn có thể thu vào `LinkedHashSet`:

```java
var words = List.of("kiwi", "pear", "kiwi", "apple");

var ordered = words.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(ordered); // [kiwi, pear, apple]
```

Đoạn trên cần import `java.util.LinkedHashSet` và `java.util.stream.Collectors`. `LinkedHashSet` có iteration order theo thứ tự chèn; việc thêm lại `kiwi` đã tồn tại không đẩy nó ra cuối. Khác với `toUnmodifiableSet`, kết quả ở đây **có thể sửa**.

Nếu cần một **snapshot không sửa được** mà vẫn có iteration order của `LinkedHashSet`, sao chép sang một backing set riêng rồi bọc:

```java
var orderedSnapshot = Collections.unmodifiableSet(
        new LinkedHashSet<>(ordered));
```

Với `ordered` là `LinkedHashSet` và backing copy không bị lộ, kết quả là unmodifiable view trên bản sao mới, có iteration order của backing `LinkedHashSet`. **Đừng thay bằng `Set.copyOf(ordered)` rồi kỳ vọng thứ tự còn giữ**, vì `Set.copyOf` không cam kết iteration order.

### 8.2. Cần thứ tự và vẫn giữ phần tử trùng

Khi mục tiêu là hiển thị mọi bản ghi đúng encounter order, dùng `List`:

```java
var orderedList = words.stream()
        .collect(Collectors.toUnmodifiableList());

// [kiwi, pear, kiwi, apple]
```

`toUnmodifiableList` là collector hiện hành từ Java 10: kết quả không sửa được, giữ phần tử trùng và có encounter order nếu nguồn có. Không dùng `Set` nếu bài toán thực sự cần giữ từng lần xuất hiện của một giá trị.

### 8.3. Cần một thứ tự được sắp xếp

Nếu muốn xuất kết quả theo thứ tự tự nhiên hoặc comparator, có thể:

```java
var set = words.stream().collect(Collectors.toUnmodifiableSet());
var sortedForDisplay = new java.util.TreeSet<>(set);
System.out.println(sortedForDisplay); // [apple, kiwi, pear]
```

`TreeSet` mặc định sửa được và dùng comparator/natural ordering. Nếu cần một giao diện đọc không sửa, có thể bọc kết quả riêng:

```java
var orderedReadOnly = Collections.unmodifiableSortedSet(
        new java.util.TreeSet<>(set));
```

Đây là một lựa chọn thiết kế có thêm bước sắp xếp và lưu cấu trúc phù hợp, không phải đặc tính có sẵn của `Collectors.toUnmodifiableSet()`.

## 9. Ngữ nghĩa khi xử lý stream song song

`toUnmodifiableSet` hoạt động với cả stream tuần tự lẫn stream song song, nhưng vẫn là **unordered collector**. Không được coi việc thu thập song song là cách giữ thứ tự chèn:

```java
var unique = List.of("A", "B", "A", "C")
        .parallelStream()
        .collect(Collectors.toUnmodifiableSet());

// Set chứa A, B, C; không có đảm bảo về iteration order
```

Collector `UNORDERED` không cho phép người lập trình khẳng định một phần tử trùng cụ thể được giữ lại. Khi các object bằng nhau theo `equals` nhưng có trường dữ liệu khác, việc chọn đại diện không được dựa trên thứ tự stream hoặc cách chia nhóm giữa các luồng.

Một collector không mang characteristic `CONCURRENT` vẫn có thể được sử dụng trong pipeline song song với cơ chế tích lũy/kết hợp phù hợp do stream framework quản lý. **Đừng suy luận rằng `UNORDERED` đồng nghĩa với việc các luồng cùng ghi vào một mutable Set dùng chung**.

Nếu cần quyết định nghiệp vụ phụ thuộc vào thứ tự hoặc đại diện cụ thể, hãy triển khai phép chọn/merge có ràng buộc rõ thay vì trông đợi vào iteration order của kết quả.

## 10. Không thể sửa Set không đồng nghĩa deep immutable

`toUnmodifiableSet` chặn các thao tác làm thay đổi cấu trúc tập kết quả, nhưng **không tự sao chép sâu mọi object phần tử**:

```java
var note = new StringBuilder("draft");
var set = java.util.stream.Stream.of(note)
        .collect(Collectors.toUnmodifiableSet());

note.append("-done");
System.out.println(set.iterator().next()); // draft-done
```

Trong ví dụ chỉ có một phần tử nên việc chọn `iterator().next()` không phụ thuộc iteration order giữa nhiều giá trị. Đối tượng `StringBuilder` bên trong vẫn mutable.

Nghiêm trọng hơn, nếu `equals` hoặc `hashCode` của phần tử phụ thuộc vào các trường có thể sửa và những trường ấy bị đổi khi phần tử đang nằm trong Set dựa trên hash, việc tra cứu `contains` hoặc logic duy nhất có thể trở nên không ổn định theo hợp đồng của Set. **Không thay đổi các thuộc tính ảnh hưởng `equals`/`hashCode` khi object đang làm phần tử Set**.

Những Set không sửa đổi được của nhóm factory mang ngữ nghĩa **value-based**; không sử dụng identity của instance Set để phối hợp đa luồng qua `synchronized`, cũng không dựa vào `==` để suy ra hai Set có cùng giá trị hay không. Dùng `equals` để so sánh tập phần tử và dùng một khóa riêng khi cần đồng bộ.

## 11. Ví dụ Java 17+ hoàn chỉnh, có output xác định

Tạo tệp `UnmodifiableSetOrderDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnmodifiableSetOrderDemo {
    static void checkFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=none");
        } catch (UnsupportedOperationException | NullPointerException ex) {
            System.out.println(name + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        var input = List.of("kiwi", "pear", "kiwi", "apple");
        var snapshot = input.stream()
                .collect(Collectors.toUnmodifiableSet());

        System.out.println("size=" + snapshot.size());
        System.out.println("sorted=" + new TreeSet<>(snapshot));
        System.out.println("hasKiwi=" + snapshot.contains("kiwi"));
        System.out.println("unorderedCollector="
                + Collectors.toUnmodifiableSet().characteristics()
                        .contains(Collector.Characteristics.UNORDERED));

        checkFailure("add", () -> snapshot.add("plum"));
        checkFailure("nullInput", () -> Stream.of("a", (String) null)
                .collect(Collectors.toUnmodifiableSet()));

        var ordered = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println("ordered=" + ordered);

        var orderedSnapshot = Collections.unmodifiableSet(
                new LinkedHashSet<>(ordered));
        ordered.add("plum");
        System.out.println("orderedAfter=" + ordered);
        System.out.println("orderedSnapshot=" + orderedSnapshot);

        var list = input.stream()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("list=" + list);
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac UnmodifiableSetOrderDemo.java
java UnmodifiableSetOrderDemo
```

Kết quả:

```text
size=3
sorted=[apple, kiwi, pear]
hasKiwi=true
unorderedCollector=true
add=UnsupportedOperationException
nullInput=NullPointerException
ordered=[kiwi, pear, apple]
orderedAfter=[kiwi, pear, apple, plum]
orderedSnapshot=[kiwi, pear, apple]
list=[kiwi, pear, kiwi, apple]
```

**Vì sao output xác định?**

- `snapshot.size()` chỉ phụ thuộc số giá trị khác nhau, không phụ thuộc iteration order.
- `new TreeSet<>(snapshot)` sắp xếp `String` trước khi in ra, nên không dựa vào thứ tự ngẫu nhiên/không bảo đảm của set gốc.
- `snapshot.contains("kiwi")` kiểm tra tư cách thành viên theo giá trị.
- Characteristic `UNORDERED` trả về `true` theo hợp đồng collector.
- `snapshot.add(...)` và trường hợp đưa `null` vào collector lần lượt gây `UnsupportedOperationException` và `NullPointerException`.
- `LinkedHashSet` trong pipeline tuần tự giữ thứ tự chèn của input, còn `orderedSnapshot` là một wrapper trên bản sao riêng nên không đổi khi `ordered.add("plum")`.
- `toUnmodifiableList` giữ cả `kiwi` lặp lại và encounter order, nên là giải pháp khác khi thứ tự và số lần xuất hiện đều quan trọng.

Chương trình cố ý **không in trực tiếp `snapshot`** để không tạo một “đầu ra chuẩn” phụ thuộc thứ tự chưa được Javadoc bảo đảm.

## 12. Những lỗi thường gặp

| Cách hiểu sai | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| “Stream đầu vào có thứ tự nên Set cũng theo thứ tự.” | Collector là `UNORDERED`; không hứa iteration order. | Dùng `LinkedHashSet` hoặc List theo nhu cầu. |
| “Gọi `sorted()` trước `toUnmodifiableSet()` sẽ có Set sắp xếp.” | Set kết quả vẫn không bảo đảm iteration order. | Sắp xếp khi xuất hoặc dùng collection có thứ tự. |
| “`toUnmodifiableSet()` giữ phần tử trùng đầu tiên.” | Collector chỉ hứa giữ **một đại diện tùy ý**. | Nếu đại diện quan trọng, triển khai quy tắc chọn rõ ràng. |
| “`toUnmodifiableSet()` chấp nhận `null` như một số HashSet.” | Đặc tả từ chối `null`, ném `NullPointerException`. | Kiểm tra/chuẩn hóa dữ liệu hoặc đổi hợp đồng. |
| “`toSet()` chắc chắn trả về `HashSet` có thể sửa.” | Javadoc không bảo đảm implementation hoặc tính sửa được. | Dùng `toCollection(HashSet::new)` hoặc factory cụ thể khi cần. |
| “`Set.copyOf(ordered)` giữ thứ tự của `LinkedHashSet`.” | `Set.copyOf` không cam kết thứ tự duyệt. | Bọc bản sao `LinkedHashSet` khi cần cả thứ tự và không sửa. |
| “`Set.of("A", "A")` xử lý trùng như collector.” | `Set.of` từ chối phần tử trùng khi tạo. | Dùng `toUnmodifiableSet` / `Set.copyOf` khi muốn loại trùng. |
| “Kết quả không sửa được nên phần tử bên trong immutable.” | Factory chỉ bảo vệ cấu trúc tập, không deep copy. | Dùng value object bất biến. |
| “Kết quả in ở máy tôi có thứ tự, vậy có thể assert chuỗi đó.” | Hành vi một JDK không tạo bảo đảm API. | So sánh tập bằng `Set.equals` hoặc sắp xếp trước khi in. |

## 13. Tự kiểm tra

Cho đoạn mã sau:

```java
var words = List.of("b", "a", "b", "c");
var set = words.stream().collect(Collectors.toUnmodifiableSet());
var list = words.stream().collect(Collectors.toUnmodifiableList());
var ordered = words.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

**Câu 1:** `set.size()` và `list.size()` là bao nhiêu?

**Đáp án:** `set.size() == 3` vì giá trị `"b"` lặp bị loại. `list.size() == 4` vì List giữ các lần xuất hiện.

**Câu 2:** `set` có được bảo đảm duyệt theo thứ tự `b, a, c` không?

**Đáp án:** Không. `toUnmodifiableSet` là collector `UNORDERED` và Set kết quả không hứa iteration order. `ordered` mới có thứ tự chèn `b, a, c` từ stream List tuần tự.

**Câu 3:** `set.add("d")` và `ordered.add("d")` có kết quả gì?

**Đáp án:** Lệnh thứ nhất ném `UnsupportedOperationException` khi chạy. Lệnh thứ hai thành công vì kết quả của `toCollection(LinkedHashSet::new)` là một `LinkedHashSet` mutable.

**Câu 4:** Nếu input có một `null` thì `toUnmodifiableSet` xử lý thế nào?

**Đáp án:** `NullPointerException`. Cần quyết định chính sách null trước khi collect, không kỳ vọng collector tự bỏ qua `null`.

**Câu 5:** Nếu hai đối tượng khác nhau nhưng `equals` coi là bằng nhau, collector giữ đối tượng nào?

**Đáp án:** Có thể giữ một đối tượng bất kỳ trong nhóm bằng nhau; không bảo đảm giữ bản đầu tiên. Nếu dự án cần quy tắc chọn đại diện, phải diễn đạt nó bằng logic riêng.

## 14. Checklist áp dụng thực tế

Trước khi dùng `Collectors.toUnmodifiableSet()`, hãy xác nhận:

1. **Nghiệp vụ cần tập các giá trị duy nhất, không cần thứ tự?** Nếu đúng, collector này phù hợp.
2. **Kết quả phải không cho sửa?** Nếu đúng, đây là bảo đảm rõ ràng mà `Collectors.toSet()` không hứa.
3. **Nguồn có thể có `null`?** Nếu có, kiểm tra hay xử lý theo nghiệp vụ trước khi collect.
4. **Có thể có những đối tượng `equals` nhau nhưng dữ liệu phụ khác nhau?** Nếu có, xác định có chấp nhận đại diện bất kỳ hay phải dùng quy tắc merge.
5. **Có yêu cầu output/test ổn định?** Đừng assert `toString()`; hãy so sánh Set theo giá trị hoặc sắp xếp riêng.
6. **Thứ tự xuất hiện có phải một phần hợp đồng API?** Nếu có, chọn `LinkedHashSet` với nguồn ordered hoặc dùng List.
7. **Phần tử có mutable không?** Cân nhắc việc thay đổi `equals`/`hashCode` và nhu cầu snapshot bất biến sâu.
8. **Có pipeline song song không?** Không phụ thuộc vị trí encounter hoặc thứ tự giữ đại diện trong quá trình gom.
9. **Có đang dùng kết quả làm khóa dựa vào identity không?** Nếu có, tách khóa khỏi tập dữ liệu value-based.

## Kết luận

`Collectors.toUnmodifiableSet()` là collector Java 10+ để chuyển một stream thành **Set không sửa đổi, không chứa `null`, loại trùng và không có thứ tự được bảo đảm**. Đặc tính **`UNORDERED`** mô tả rằng thứ tự đầu vào không phải là hợp đồng của phép thu thập.

Khi cần **thứ tự xuất hiện**, dùng collector cho `LinkedHashSet`; khi cần **giữ cả phần tử trùng**, dùng `toUnmodifiableList`; khi chỉ cần **giá trị duy nhất và kết quả không thể sửa**, `toUnmodifiableSet` là lựa chọn trực tiếp.

## Tài liệu chính thức và nguồn học thêm

- [Java SE 26 — `Collectors.toUnmodifiableSet()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()): collector `UNORDERED`, từ chối null, giữ một phần tử bất kỳ trong các phần tử bằng nhau, có từ Java 10.
- [Java SE 26 — `Collector.Characteristics`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html): ý nghĩa `UNORDERED`, `CONCURRENT` và `IDENTITY_FINISH`.
- [Java SE 26 — `Set`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html): hợp đồng loại trùng, `equals`, iterator và các tập không sửa đổi.
- [Java SE 26 — `Collectors.toCollection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): lựa chọn implementation cụ thể như `LinkedHashSet`.
- [Oracle Java SE 26 Core Libraries — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html): so sánh các collector và lưu ý iteration order không được bảo đảm.
