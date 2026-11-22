# Thứ tự gặp phần tử và thứ tự của danh sách kết quả khi dùng Collector trong Java

*Chủ đề: Java 10 — Collector danh sách và tập. Nội dung dùng các quy tắc Stream, Collector, List và Set đang được hỗ trợ trên Java 17+ và các JDK hiện đại. Những ví dụ dùng `var` giữ nguyên hệ thống kiểu tĩnh của Java.*

## 1. Bài toán: “giữ nguyên thứ tự” thực sự có nghĩa gì?

Khi thu thập dữ liệu từ `Stream` thành một `List` hoặc `Set`, có hai câu hỏi dễ bị nhầm:

1. **Stream đầu vào có thứ tự gặp phần tử (*encounter order*) hay không?**
2. **Bộ thu thập có tạo kết quả theo thứ tự ấy hay không?**

Ví dụ nguồn là danh sách:

~~~java
var source = List.of("pear", "apple", "pear", "banana");
~~~

Khi duyệt `source.stream()` theo thứ tự gặp phần tử, các giá trị là:

~~~text
pear -> apple -> pear -> banana
~~~

Nếu chỉ chuyển thành chữ hoa rồi thu về danh sách theo một collector giữ thứ tự, kết quả phải là:

~~~text
[PEAR, APPLE, PEAR, BANANA]
~~~

Ở đây hai phần tử `"pear"` ban đầu **vẫn xuất hiện hai lần**, bởi `List` chấp nhận phần tử trùng. “Giữ thứ tự” không đồng nghĩa “loại trùng”; đó là hai yêu cầu độc lập.

Ngược lại, nếu biến đầu vào là `HashSet` hoặc `Set.of(...)`, API **không cam kết thứ tự gặp phần tử có ý nghĩa ổn định** cho mục đích trình bày. Việc thu về một `List` không tự khôi phục “thứ tự ban đầu” không tồn tại trong hợp đồng nguồn.

**Nguyên tắc trung tâm:** Collector không thể giữ một encounter order mà upstream không bảo đảm; khi upstream có encounter order, các cách gom **list có bảo đảm theo encounter order** sẽ duy trì nó, trừ khi pipeline đã chủ động thay đổi hoặc gỡ ràng buộc đó.

## 2. Encounter order là thuộc tính của nguồn và pipeline

Encounter order là thứ tự logic mà các phần tử được đưa qua một stream **có thứ tự**. Nó không đồng nghĩa với thời điểm các tác vụ thật sự chạy trên thread.

Một số nguồn phổ biến:

| Nguồn | Encounter order đáng dựa vào? | Ý nghĩa |
| --- | --- | --- |
| `List.of("A","B","C").stream()` | Có | Thứ tự vị trí của `List` |
| `ArrayList.stream()` | Có | Theo chỉ số danh sách |
| `Arrays.stream(array)` | Có | Theo thứ tự chỉ số mảng |
| `Stream.of("A","B","C")` | Có | Theo thứ tự đối số |
| `LinkedHashSet.stream()` | Có | Theo thứ tự duyệt được tập này bảo đảm, thường là thứ tự thêm |
| `TreeSet.stream()` | Có | Theo thứ tự sắp xếp của `TreeSet` |
| `HashSet.stream()` | Không được cam kết | Thứ tự duyệt phụ thuộc triển khai và trạng thái |
| `Set.of(...).stream()` | Không được cam kết | Không dựa vào thứ tự đối số khi in/duyệt |
| `HashMap.keySet().stream()` | Không được cam kết | Thứ tự khóa không xác định theo hợp đồng `HashMap` |
| `Stream.generate(supplier)` | Không được cam kết là có thứ tự | Stream được tạo không có encounter order theo hợp đồng |

Nguồn `Set` không phải lúc nào cũng unordered: `LinkedHashSet` và `TreeSet` có bảo đảm thứ tự duyệt, còn `HashSet` thì không. Vì vậy, chỉ nhìn thấy tên interface `Set` không đủ để kết luận. Hãy xem **hợp đồng của cấu trúc nguồn** và các thao tác trung gian.

Ví dụ:

~~~java
var data = List.of("C", "A", "B");
var kept = data.stream().toList();       // [C, A, B]
var sorted = data.stream().sorted().toList(); // [A, B, C]
~~~

`sorted()` đã **thiết lập một thứ tự mới** theo thứ tự tự nhiên của `String`, không phải giữ nguyên thứ tự nguồn. Sau đó `toList()` giữ thứ tự được xác định bởi pipeline sau `sorted()`.

### Một lưu ý về `Set.of` và `HashSet`

Không nên viết test sau:

~~~java
var names = Set.of("An", "Binh", "Chi");
var list = names.stream().toList();
// Sai nếu test yêu cầu list.equals(List.of("An", "Binh", "Chi")).
~~~

Cùng một máy có thể tình cờ in đúng thứ tự ấy nhiều lần, nhưng đó không phải bảo đảm của API. Muốn thứ tự dự đoán được, hãy **sắp xếp** hoặc bắt đầu từ nguồn có thứ tự.

## 3. Các cách gom thành `List` có bảo đảm gì?

### 3.1. `Collectors.toList()`

~~~java
var names = List.of("B", "A", "B", "C");
var result = names.stream().collect(Collectors.toList());
// result: [B, A, B, C]
~~~

Với stream **có encounter order**, collector `toList()` gom các phần tử theo thứ tự ấy, không tự lọc phần tử trùng. Nếu upstream chứa phần tử được lặp, kết quả vẫn chứa chúng.

**Quan trọng:** `Collectors.toList()` **không cam kết** lớp triển khai cụ thể, khả năng sửa, serializability hay thread-safety của `List` thu được. Trên JDK phổ biến bạn có thể thấy một danh sách mutable, nhưng không nên viết API/test lệ thuộc vào điều đó.

Muốn chắc chắn có `ArrayList` để chỉnh sửa, dùng:

~~~java
var mutable = names.stream()
        .collect(Collectors.toCollection(ArrayList::new));
mutable.add("D"); // Hợp lệ: kết quả là ArrayList
~~~

Nếu mục tiêu là danh sách không thể sửa, xem `Stream.toList()` và `Collectors.toUnmodifiableList()` dưới đây.

### 3.2. `Collectors.toUnmodifiableList()` — từ Java 10

~~~java
var result = names.stream()
        .collect(Collectors.toUnmodifiableList());
// Thứ tự giữ theo encounter order: [B, A, B, C]
// result.add("D"); // UnsupportedOperationException
~~~

Collector này tạo `List` không thể sửa, có thứ tự phần tử theo encounter order khi nguồn có thứ tự. Nó **từ chối phần tử `null`**: nếu stream đưa ra giá trị null, thao tác collect ném `NullPointerException`.

Đây là một trong các API collection hiện đại có từ Java 10, vẫn được sử dụng trong JDK hiện nay.

### 3.3. `Stream.toList()` — từ Java 16

~~~java
var result = names.stream().toList();
// Thứ tự giữ theo encounter order: [B, A, B, C]
// result.add("D"); // UnsupportedOperationException
~~~

`Stream.toList()` trả một `List` **không thể sửa**. Khi stream có encounter order, kết quả chứa phần tử theo thứ tự đó. Không cam kết lớp triển khai cụ thể của danh sách.

Khác biệt thực tế:

~~~java
var containsNull = Stream.<String>of("A", null).toList();
// Hợp lệ, kết quả có phần tử null.

// Dòng này ném NullPointerException:
var noNulls = Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableList());
~~~

Cả hai có thể cho danh sách không thể sửa, nhưng **chính sách null khác nhau**. Bài này tập trung vào thứ tự, song khi chọn API cần xét cả hợp đồng null.

### 3.4. `Collectors.toCollection(ArrayList::new)`

~~~java
var collected = names.stream()
        .collect(Collectors.toCollection(ArrayList::new));
// Là ArrayList với phần tử theo encounter order.
collected.add("D");
~~~

Cách này cho phép chọn **supplier** tạo collection, nên hợp lý khi cần kiểu cụ thể và khả năng sửa được. Với nguồn có encounter order và cấu trúc kết quả là `ArrayList`, các phần tử được ghi vào đúng thứ tự.

Không nên cố đoán `Collectors.toList()` luôn tạo `ArrayList` để thay cho cách viết này; hãy ghi rõ ý định bằng `toCollection(ArrayList::new)`.

### 3.5. `List.copyOf` sau khi gom

~~~java
var mutable = names.stream()
        .collect(Collectors.toCollection(ArrayList::new));
var published = List.copyOf(mutable);
mutable.add("D");
// published vẫn chứa [B, A, B, C].
~~~

`List.copyOf` bảo toàn thứ tự duyệt của collection được copy, tạo kết quả không thể sửa và không phản ánh các thay đổi cấu trúc/thay phần tử về sau ở nguồn. Nó **từ chối phần tử null**. Không dựa vào identity của kết quả: `copyOf` có thể tái sử dụng nguồn unmodifiable phù hợp.

## 4. Bảng so sánh các cách gom danh sách và tập

| API | Loại kết quả | Giữ encounter order khi upstream có thứ tự? | Có thể sửa? |
| --- | --- | --- | --- |
| `collect(Collectors.toList())` | `List<T>` | **Có** | Không được API cam kết |
| `collect(Collectors.toUnmodifiableList())` | `List<T>` | **Có** | Không |
| `stream.toList()` | `List<T>` | **Có** | Không |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | **Có** | Có |
| `collect(Collectors.toSet())` | `Set<T>` | **Không cam kết thứ tự duyệt** | Không được API cam kết |
| `collect(Collectors.toUnmodifiableSet())` | `Set<T>` | **Không cam kết thứ tự duyệt** | Không |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` | **Có**, theo thứ tự xuất hiện đầu tiên của các giá trị khác nhau | Có |
| `Set.copyOf(collection)` | `Set<T>` | **Không cam kết thứ tự duyệt** | Không |
| `Collections.unmodifiableSet(new LinkedHashSet<>(source))` | Read-only view của `LinkedHashSet` | **Có**, nếu backing set được duy trì đúng | Không qua wrapper |

Các cột trong bảng là **bảo đảm của API**, không phải một snapshot tình cờ của một phiên bản JDK. Với stream **không có encounter order**, ngay cả collector danh sách cũng không thể hứa phục hồi một trình tự nguồn vốn không được xác định.

Nếu cần kết quả có thứ tự và không thể sửa, `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` thường dễ đọc hơn. Khi cần loại trùng **và** giữ thứ tự xuất hiện đầu tiên, xem mục `LinkedHashSet`.

## 5. `List` giữ thứ tự và có thể chứa trùng; `Set` biểu diễn tính duy nhất

Cho dữ liệu:

~~~java
var source = List.of("A", "B", "A", "C");
~~~

Kết quả nếu thu danh sách:

~~~java
var list = source.stream().toList(); // [A, B, A, C]
~~~

Các giá trị lặp được giữ lại. Nhưng:

~~~java
var set = source.stream().collect(Collectors.toSet());
System.out.println(set.size()); // 3
// Không cam kết thứ tự duyệt/in phần tử.
~~~

`Set` chỉ có một phần tử đại diện cho mỗi giá trị khác nhau theo `equals`. `Collectors.toSet()` được mô tả là **unordered collector**, nên không được dựa vào thứ tự kết quả, kể cả khi upstream đến từ `List` có thứ tự.

**Cảnh báo thường gặp:** `Set.copyOf(source)` cũng cho set không thể sửa nhưng **không cam kết thứ tự**. Đừng dùng `Set.copyOf` để “đóng băng thứ tự” từ một danh sách.

Khi cần tạo một danh sách **các giá trị duy nhất theo thứ tự xuất hiện đầu tiên**, có hai hướng thường dùng:

~~~java
var uniqueList = source.stream().distinct().toList();
// [A, B, C] với ordered stream.

var uniqueSet = source.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
// LinkedHashSet duyệt theo thứ tự A, B, C.
~~~

Khác biệt:

- `uniqueList` là một `List` không thể sửa trên Java 16+ với thứ tự gặp phần tử theo `distinct()`.
- `uniqueSet` là `LinkedHashSet` **mutable** có thứ tự duyệt xác định theo thứ tự thêm phần tử.
- `distinct()` trên stream **có encounter order** bảo đảm giữ phần tử đầu tiên trong mỗi nhóm phần tử bằng nhau (*stable for ordered streams*).
- Nếu stream không có encounter order, việc chọn đại diện hoặc thứ tự giữa các giá trị không cần phản ánh lần xuất hiện đầu tiên theo một thứ tự nguồn nào đó.

## 6. `LinkedHashSet` — khi vừa cần tập vừa cần thứ tự

`LinkedHashSet` duy trì một thứ tự duyệt xác định (thông thường theo thứ tự chèn); thêm lại một phần tử đã có không tạo phần tử thứ hai hoặc thay vị trí chèn ban đầu trong các thao tác chèn thông thường.

~~~java
var names = List.of("pear", "apple", "pear", "banana");

var set = names.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(new ArrayList<>(set)); // [pear, apple, banana]
~~~

Đây là cách rõ ràng khi mục tiêu là **tập giá trị duy nhất** nhưng người dùng cũng mong thấy thứ tự xuất hiện đầu tiên từ danh sách nhập liệu.

Nếu muốn **không cho caller sửa** tập đó, có thể tạo một private backing set mới rồi chỉ xuất bản wrapper:

~~~java
var ordered = new LinkedHashSet<>(names);
Set<String> readOnlyOrdered = Collections.unmodifiableSet(ordered);
~~~

Với mã trên, `readOnlyOrdered` không thể sửa qua API wrapper và duyệt theo thứ tự của `LinkedHashSet` nền. Nhưng `ordered` vẫn là một biến mutable: nếu ai đó giữ tham chiếu và sửa nó, wrapper **sẽ phản ánh** thay đổi đó. Để có API read-only ổn định, hãy xây dựng backing set riêng ở phạm vi kín và không để lọt tham chiếu có thể sửa ra ngoài.

Một hàm giúp đóng gói cách này:

~~~java
static <T> Set<T> orderedReadOnlySet(Collection<? extends T> input) {
    return Collections.unmodifiableSet(new LinkedHashSet<>(input));
}
~~~

Đây là một phương thức minh họa đặt trong lớp có import `Set`, `Collection`, `Collections`, `LinkedHashSet`. Nó tạo một backing set mới và chỉ trả wrapper, nhờ đó caller không trực tiếp có tham chiếu mutable. Không khẳng định đây là “deep immutable”: các phần tử có thể mutable, và phương thức cần hợp đồng rõ về null. Nếu đầu vào chứa null, `LinkedHashSet` có thể lưu null; khác với `Set.copyOf` vốn từ chối null.

**Nếu đầu ra về bản chất là một danh sách để hiển thị,** không cần cố giữ nó ở dạng `Set`: `stream.distinct().toList()` thường đơn giản hơn.

## 7. `sorted()` thay đổi thứ tự theo tiêu chí mới

`sorted()` tạo một encounter order theo comparator hoặc thứ tự tự nhiên, kể cả khi upstream không có thứ tự xác định:

~~~java
var names = List.of("pear", "apple", "pear", "banana");
var alphabetically = names.stream().sorted().toList();
// [apple, banana, pear, pear]
~~~

Khi có nhiều phần tử bằng nhau theo comparator, `sorted()` bảo đảm **ổn định** đối với stream **có thứ tự**: các phần tử được xem là bằng nhau bởi comparator giữ nguyên thứ tự tương đối ban đầu. Với stream không có thứ tự, sự ổn định tương đối giữa các phần tử bằng nhau **không được bảo đảm**.

Ví dụ danh sách đối tượng:

~~~java
record Item(String code, int priority) { }

var source = List.of(
        new Item("B", 2),
        new Item("A", 1),
        new Item("C", 2));

var sorted = source.stream()
        .sorted(Comparator.comparingInt(Item::priority))
        .toList();

// Vì stream có thứ tự và thuật toán sorted ổn định:
// các Item có priority=2 vẫn theo thứ tự B rồi C.
~~~

Đoạn mã cần nằm trong lớp/phương thức với import `List` và `Comparator`; nó không phải tệp Java độc lập. Trong ứng dụng thật, khi cần thứ tự hoàn toàn xác định kể cả các phần tử có tiêu chí chính bằng nhau, có thể thêm tie-breaker:

~~~java
var sorted = source.stream()
        .sorted(Comparator.comparingInt(Item::priority)
                .thenComparing(Item::code))
        .toList();
~~~

Lúc đó, thứ tự không phụ thuộc vào sự ổn định tương đối với comparator chỉ xét `priority`. `sorted()` có chi phí sắp xếp; không tự động chèn nó chỉ để che vấn đề nguồn vốn không có encounter order.

## 8. `distinct()` và ý nghĩa “xuất hiện đầu tiên”

Với một stream từ `List`:

~~~java
var names = List.of("B", "A", "B", "C", "A");
var unique = names.stream().distinct().toList();
// [B, A, C]
~~~

`distinct()` dựa vào `Object.equals`. Vì upstream có thứ tự, nó giữ đại diện **đầu tiên** của mỗi giá trị trùng. Nếu chuyển thành:

~~~java
var unique = names.parallelStream()
        .distinct()
        .toList();
~~~

thì với nguồn có encounter order, kết quả vẫn phải giữ thứ tự lần xuất hiện đầu tiên. Việc thực thi song song có thể phức tạp hơn/đắt hơn khi phải duy trì tính ổn định.

Ngược lại:

~~~java
var unique = names.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

`unordered()` **gỡ bỏ ràng buộc encounter order**. Không được kỳ vọng đại diện trùng lặp và thứ tự kết quả vẫn là “lần đầu trong danh sách” nữa. Kết quả cụ thể có thể tình cờ giống nhau trong một lần chạy; đó không phải bảo đảm.

Nếu nghiệp vụ cần “lấy bản ghi đầu tiên theo thứ tự nhập” để quyết định ưu tiên, không dùng `unordered()` trước `distinct()`.

## 9. Song song không đồng nghĩa danh sách kết quả bị đảo thứ tự

Một nhầm lẫn phổ biến là `parallelStream()` luôn trả kết quả lộn xộn. Với ordered stream, điều này **không đúng** cho các terminal operation có bảo đảm giữ encounter order:

~~~java
var names = List.of("B", "A", "C");

var sequential = names.stream()
        .map(String::toLowerCase)
        .toList();

var parallel = names.parallelStream()
        .map(String::toLowerCase)
        .toList();

// Cả hai cùng [b, a, c].
~~~

Mặc dù các lời gọi `map` có thể được tính ở các thread khác nhau và **không theo thứ tự thời gian**, `Stream.toList()` tái lập encounter order cho kết quả của ordered stream.

Điều tương tự áp dụng cho `collect(Collectors.toList())` và `collect(Collectors.toUnmodifiableList())` khi upstream có thứ tự, miễn là pipeline không chủ động làm mất ràng buộc đó.

### 9.1. `forEach` khác `forEachOrdered`

~~~java
var names = List.of("A", "B", "C", "D");

// Không dựa vào thứ tự in khi chạy parallel:
names.parallelStream().forEach(System.out::println);

// Có bảo đảm thực hiện action theo encounter order:
names.parallelStream().forEachOrdered(System.out::println);
~~~

`forEachOrdered` bảo đảm hành động được thực hiện theo encounter order của stream nếu có. Nó không tự tạo thứ tự cho một stream vốn unordered; và vì phải giữ thứ tự, nó có thể làm giảm một phần lợi ích song song. Đây là **terminal operation tạo side effect**, không phải collector trả `List`.

Không dùng hành vi của `peek` hay thứ tự dòng log từ pipeline song song để kết luận rằng danh sách cuối cùng bị mất thứ tự: hai loại quan sát khác nhau.

### 9.2. Khi nào `unordered()` hữu ích?

Nếu nghiệp vụ **không quan tâm thứ tự**, việc cho phép pipeline unordered đôi khi mở đường cho tối ưu hóa, nhất là với một số thao tác song song có trạng thái. Nhưng chỉ dùng khi yêu cầu nghiệp vụ thật sự không đòi thứ tự.

Ví dụ nếu mục tiêu là kiểm tra tư cách thành viên, tập giá trị có thể phù hợp hơn danh sách hiển thị. Ngược lại, với dữ liệu cần thứ tự xếp hạng, thứ tự các bước thao tác hoặc thứ tự thời gian, **không** bỏ encounter order chỉ vì hy vọng tăng tốc.

## 10. Chương trình Java 17+ hoàn chỉnh, có đầu ra xác định

Đoạn sau kiểm tra sự khác biệt giữa danh sách, tập, nguồn `LinkedHashSet`, xử lý trùng, `sorted()` và ordered parallel stream. Những phần không có bảo đảm thứ tự như `Collectors.toSet()` chỉ được in **kích thước**, tránh viết mẫu output dựa trên thứ tự tình cờ.

~~~java
// File: EncounterOrderCollectorsDemo.java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class EncounterOrderCollectorsDemo {
    public static void main(String[] args) {
        var input = List.of("pear", "apple", "pear", "banana");

        var collected = input.stream()
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        var unmodifiable = input.stream()
                .map(String::toUpperCase)
                .collect(Collectors.toUnmodifiableList());
        var streamList = input.stream()
                .map(String::toUpperCase)
                .toList();

        var distinct = input.stream().distinct().toList();
        var sorted = input.stream().sorted().toList();
        var parallel = input.parallelStream()
                .map(String::toUpperCase).toList();

        var linkedSet = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        var plainSet = input.stream().collect(Collectors.toSet());

        var linkedInput = new LinkedHashSet<>(input);
        var linkedList = linkedInput.stream().toList();

        var explicitlyMutable = input.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        explicitlyMutable.add("kiwi");

        var orderedSideEffects = new StringJoiner(",");
        input.parallelStream().forEachOrdered(orderedSideEffects::add);

        System.out.println("input = " + input);
        System.out.println("Collectors.toList = " + collected);
        System.out.println("toUnmodifiableList = " + unmodifiable);
        System.out.println("Stream.toList = " + streamList);
        System.out.println("distinct = " + distinct);
        System.out.println("sorted = " + sorted);
        System.out.println("parallel toList = " + parallel);
        System.out.println("LinkedHashSet order = " + new ArrayList<>(linkedSet));
        System.out.println("toSet size = " + plainSet.size());
        System.out.println("LinkedHashSet source = " + linkedList);
        System.out.println("mutable last = "
                + explicitlyMutable.get(explicitlyMutable.size() - 1));
        System.out.println("forEachOrdered = " + orderedSideEffects);

        try {
            streamList.add("MELON");
            System.out.println("Stream.toList blocks add = false");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Stream.toList blocks add = true");
        }
    }
}
~~~

Lưu thành `EncounterOrderCollectorsDemo.java`, biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 EncounterOrderCollectorsDemo.java
java EncounterOrderCollectorsDemo
~~~

Stdout đã kiểm chứng:

~~~text
input = [pear, apple, pear, banana]
Collectors.toList = [PEAR, APPLE, PEAR, BANANA]
toUnmodifiableList = [PEAR, APPLE, PEAR, BANANA]
Stream.toList = [PEAR, APPLE, PEAR, BANANA]
distinct = [pear, apple, banana]
sorted = [apple, banana, pear, pear]
parallel toList = [PEAR, APPLE, PEAR, BANANA]
LinkedHashSet order = [pear, apple, banana]
toSet size = 3
LinkedHashSet source = [pear, apple, banana]
mutable last = kiwi
forEachOrdered = pear,apple,pear,banana
Stream.toList blocks add = true
~~~

Giải thích:

1. Ba cách gom danh sách `Collectors.toList()`, `Collectors.toUnmodifiableList()` và `Stream.toList()` cùng giữ encounter order của nguồn `List` và của phép `map`.
2. `distinct()` loại bản ghi `pear` lặp lại, giữ thứ tự xuất hiện đầu tiên; `sorted()` sắp xếp các chuỗi theo thứ tự tự nhiên.
3. `parallelStream().map(...).toList()` vẫn trả danh sách theo encounter order, dù tính toán có thể chạy song song.
4. `toCollection(LinkedHashSet::new)` cho tập có thứ tự duyệt lần xuất hiện đầu; chương trình chuyển tập sang `ArrayList` trước khi in để dễ quan sát.
5. `Collectors.toSet()` không cam kết thứ tự; vì thế chỉ in kích thước là 3, không dựa vào `toString()` của tập.
6. `LinkedHashSet` là nguồn có thứ tự; `linkedInput.stream().toList()` giữ thứ tự duyệt xác định ấy.
7. `toCollection(ArrayList::new)` trả danh sách mutable, nên thêm `kiwi` thành công.
8. `forEachOrdered` trên stream song song giữ thứ tự action theo nguồn và tạo chuỗi `pear,apple,pear,banana`. Ví dụ đơn giản dùng `StringJoiner` để minh họa; trong hệ thống thực tế, nên ưu tiên các phép biến đổi không có side effect khi làm việc song song.
9. `Stream.toList()` trả unmodifiable list, nên thao tác `add` bị chặn.

## 11. Một số tình huống thực tế và cách chọn

### 11.1. Danh sách sản phẩm theo thứ tự tìm kiếm

Nếu API tìm kiếm trả một `List<Product>` đã được xếp hạng, việc biến đổi để hiển thị thường phải giữ thứ tự:

~~~java
// Mã minh họa khi Product có method title() và items đã được khai báo.
var titles = items.stream()
        .map(Product::title)
        .toList();
~~~

Kết quả vẫn theo thứ tự của `items` nếu upstream có encounter order. **Đừng đổi sang `toSet()`**, vì nó làm mất thứ tự và có thể gom các tên trùng; đó là thay đổi nghiệp vụ.

### 11.2. Danh sách người tham dự từ lần xuất hiện đầu tiên

~~~java
var attendees = List.of("An", "Bình", "An", "Chi");
var uniqueAttendees = attendees.stream()
        .distinct()
        .toList(); // [An, Bình, Chi]
~~~

Nếu cần hiển thị người theo lần xuất hiện đầu tiên, `distinct().toList()` thể hiện ý định rất rõ. Nếu cần tập duy nhất có thể thêm/xóa về sau, `toCollection(LinkedHashSet::new)` có thể thích hợp.

### 11.3. Danh sách từ kết quả tra cứu không có thứ tự

Giả sử dữ liệu đến từ `HashMap.values()` hoặc một tập `HashSet`. Nếu cần đầu ra xác định, hãy sắp xếp:

~~~java
var values = new HashSet<>(List.of("B", "A", "C"));
var display = values.stream()
        .sorted()
        .toList(); // [A, B, C]
~~~

Không nên tạo `List.copyOf(values)` rồi giả định thứ tự là thứ tự người dùng nhập ban đầu. Việc tạo list có thể cố định thứ tự **một lần duyệt cụ thể**, nhưng thứ tự đó không phải quy tắc nghiệp vụ đáng dựa vào.

### 11.4. Kết quả có thể sửa để tiếp tục xử lý

~~~java
var mutable = input.stream()
        .filter(s -> !s.isBlank())
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("new");
~~~

Ở đây việc chọn `ArrayList` và mutability là quyết định **rõ ràng**, không vô tình trông đợi `Collectors.toList()` luôn trả list có thể sửa.

### 11.5. Danh sách công khai không thể sửa

~~~java
var published = input.stream()
        .map(String::strip)
        .collect(Collectors.toUnmodifiableList());
~~~

Nếu đầu vào có thể chứa null, biểu thức `String::strip` đã không xử lý được null và sẽ ném ngoại lệ khi mapper chạy. Cần xác định chính sách null ở ranh giới nhận dữ liệu, không chỉ dựa vào collector. `Collectors.toUnmodifiableList` cũng tự từ chối null nếu có phần tử null đi tới collector.

### 11.6. Tập mã không cần thứ tự

~~~java
var allowedCodes = source.stream()
        .collect(Collectors.toUnmodifiableSet());
~~~

Cách này hợp lý nếu mục tiêu là các mã không trùng và không cho sửa, **không có yêu cầu thứ tự**. Nếu một nơi khác dùng kết quả để hiển thị theo thứ tự ưu tiên, cần một cấu trúc/tiêu chí sắp xếp riêng.

## 12. Bẫy về thứ tự trong pipeline dài

### 12.1. Thứ tự gặp phần tử không phải thứ tự chạy của mọi callback

~~~java
var result = items.parallelStream()
        .map(item -> transform(item))
        .toList();
~~~

Với nguồn có thứ tự, danh sách cuối vẫn có encounter order. Nhưng `transform` có thể thực thi ở các thread khác nhau và theo thứ tự thời gian không giống thứ tự phần tử trong list. Vì thế **tránh dựa vào side effect** bên trong `map` để ghi thứ tự vào cơ sở dữ liệu, tạo số thứ tự nghiệp vụ hoặc cập nhật biến chia sẻ mà không có đồng bộ.

Nếu cần gán số thứ tự ổn định, hãy dùng chỉ số nguồn hoặc tạo cặp chỉ số/giá trị theo một cách có ràng buộc thứ tự rõ; đừng dùng “thời điểm callback được chạy”.

### 12.2. `limit` và `skip` trên unordered stream

Với ordered stream:

~~~java
var names = List.of("A", "B", "C", "D");
var firstTwo = names.stream().limit(2).toList(); // [A, B]
var afterTwo = names.stream().skip(2).toList();  // [C, D]
~~~

Với unordered stream, “hai phần tử đầu” không có cùng ý nghĩa cố định: `limit(2)` được phép chọn bất kỳ hai phần tử phù hợp theo các bảo đảm của pipeline. Không dùng `unordered()` nếu quy tắc xử lý đòi “đầu tiên theo thời gian/ưu tiên”.

### 12.3. `sorted()` không phải giải pháp cho mọi trường hợp

`sorted()` làm rõ một thứ tự theo comparator, nhưng nếu cần thứ tự **phát sinh từ nghiệp vụ** như “mục nào được chọn trước”, việc sắp xếp theo bảng chữ cái sẽ **thay đổi ý nghĩa**. Phải nhận diện đúng yêu cầu: bảo toàn thứ tự nguồn, hay thiết lập thứ tự mới.

Nếu muốn đầu ra ổn định bất kể nguồn là `HashSet`, sắp xếp theo một khóa có tính quyết định. Với nhiều phần tử có khóa sắp xếp bằng nhau, thêm tie-breaker phù hợp để tránh kết quả quan sát phụ thuộc thứ tự đầu vào không được cam kết.

### 12.4. Không nhầm thứ tự của map với thứ tự list

`Collectors.groupingBy(...)` thường trả một `Map`, và API không nên được hiểu là cam kết iteration order của khóa trừ khi chỉ rõ map supplier. `groupingByConcurrent` còn có các đặc tính thực thi khác. Đừng lấy thứ tự in `Map` làm bằng chứng cho thứ tự của các `List` giá trị. Nếu bài toán là một danh sách kết quả có thứ tự, cần kiểm tra từ **nguồn stream tới collector của danh sách** ở từng tầng.

## 13. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`Collectors.toList()` luôn trả `ArrayList`.” | Không có cam kết về implementation hay mutability. |
| “`List` thu được từ stream luôn có thứ tự giống danh sách nhập.” | Chỉ khi upstream có encounter order và pipeline/collector giữ nó. |
| “`Collectors.toSet()` giữ thứ tự nguồn List.” | Không có cam kết; collector này unordered. |
| “`Set.copyOf(list)` đóng băng thứ tự chèn.” | Không; nó tạo tập unmodifiable, không cam kết thứ tự duyệt. |
| “`LinkedHashSet` xóa hết thông tin thứ tự.” | Không; nó có thứ tự duyệt xác định, thường theo thứ tự chèn. |
| “`parallelStream()` chắc chắn làm kết quả `toList()` bị xáo trộn.” | Không nếu upstream có encounter order và dùng terminal operation giữ thứ tự. |
| “Khi danh sách cuối đúng thứ tự, callback `map` cũng chạy tuần tự đúng thứ tự.” | Không; thứ tự tính toán và thứ tự kết quả là hai chuyện khác. |
| “`forEach` và `forEachOrdered` như nhau trên parallel stream.” | `forEachOrdered` duy trì encounter order cho action khi stream có thứ tự. |
| “`unordered()` là một hàm trộn ngẫu nhiên.” | Không; nó chỉ loại bỏ ràng buộc thứ tự, không hứa tạo thứ tự khác. |
| “`sorted()` luôn giữ nguyên thứ tự nguồn.” | Không; nó xác lập thứ tự theo comparator/thứ tự tự nhiên. |
| “`distinct()` luôn giữ đối tượng xuất hiện đầu tiên bất kể upstream.” | Bảo đảm ổn định chỉ dành cho ordered streams. |
| “`Stream.toList()` và `Collectors.toUnmodifiableList()` cùng xử lý null.” | Không; `toUnmodifiableList` từ chối null, còn `Stream.toList` không áp đặt cấm null. |
| “Collection không thể sửa thì mọi phần tử bên trong cũng immutable.” | Không; mutability của phần tử là vấn đề riêng. |

## 14. Bài tập có đáp án

### Bài 1 — Bảo toàn thứ tự và phần tử trùng

~~~java
var input = List.of("C", "A", "C", "B");
var result = input.stream()
        .collect(Collectors.toUnmodifiableList());
~~~

**Hỏi:** `result` là gì?

**Đáp án:** `[C, A, C, B]`. Ordered stream giữ thứ tự; collector danh sách không loại trùng; kết quả không thể sửa.

### Bài 2 — Nguồn không bảo đảm thứ tự

~~~java
var input = new HashSet<>(List.of("C", "A", "B"));
var result = input.stream().toList();
~~~

**Hỏi:** Có khẳng định `result.equals(List.of("C","A","B"))` được không?

**Đáp án:** Không. `HashSet` không cam kết encounter order; phải dùng `sorted()` hoặc nguồn có thứ tự nếu cần quy tắc cụ thể.

### Bài 3 — Giữ thứ tự xuất hiện đầu tiên nhưng loại trùng

~~~java
var input = List.of("B", "A", "B", "C", "A");
~~~

**Yêu cầu:** Tạo danh sách không thể sửa có thứ tự `[B, A, C]`.

**Đáp án:**

~~~java
var result = input.stream().distinct().toList();
~~~

Nguồn là `List` ordered, nên `distinct` ổn định theo lần gặp đầu tiên.

### Bài 4 — Vì sao không thể dựa vào `toSet()` để hiển thị?

~~~java
var result = List.of("B", "A", "C").stream()
        .collect(Collectors.toSet());
~~~

**Đáp án:** `Collectors.toSet()` không bảo đảm kiểu cụ thể hay thứ tự duyệt. Set thích hợp cho tính duy nhất/tư cách thành viên, không phải thứ tự danh sách hiển thị.

### Bài 5 — Cần set có thứ tự xuất hiện đầu tiên

**Đáp án:**

~~~java
var orderedSet = input.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

Nó là `LinkedHashSet` mutable. Nếu chỉ cần danh sách cho UI, có thể cân nhắc `input.stream().distinct().toList()` thay vì tập.

### Bài 6 — Song song

~~~java
var data = List.of(3, 1, 2);
var result = data.parallelStream().map(n -> n * 2).toList();
~~~

**Đáp án:** `[6, 2, 4]`. Dù thực thi song song, nguồn có encounter order và `toList()` giữ nó. Không suy ra các phép nhân được chạy theo thứ tự thời gian 3, 1, 2.

### Bài 7 — `unordered()`

~~~java
var result = List.of("B", "A", "B")
        .parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

**Hỏi:** Có thể yêu cầu kết quả luôn là `[B, A]` không?

**Đáp án:** Không. `unordered()` gỡ ràng buộc encounter order; kết quả không nhất thiết theo thứ tự xuất hiện đầu tiên. Việc một lần chạy cho `[B, A]` không phải hợp đồng.

### Bài 8 — Thay đổi chính sách sắp xếp

~~~java
var source = List.of("pear", "apple", "banana");
var output = source.stream().sorted().toList();
~~~

**Đáp án:** `[apple, banana, pear]`. `sorted()` chủ động thay đổi thứ tự nguồn; nếu yêu cầu giữ thứ tự nhập, không dùng `sorted()`.

### Bài 9 — Cần sửa danh sách kết quả

**Hỏi:** Nên chọn `Collectors.toList()` hay cách nào nếu caller chắc chắn cần `add`?

**Đáp án:**

~~~java
var result = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
result.add("new");
~~~

`toCollection(ArrayList::new)` tạo rõ một `ArrayList` mutable. Không dựa vào mutability không được cam kết của `Collectors.toList()`.

### Bài 10 — Hai cách gom unmodifiable khác null thế nào?

~~~java
var x = Stream.<String>of("A", null).toList();
var y = Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableList());
~~~

**Đáp án:** `x` chứa hai phần tử trong một unmodifiable list, gồm một `null`; việc tạo `y` ném `NullPointerException`. Khác biệt này độc lập với câu hỏi giữ thứ tự gặp phần tử.

## 15. Checklist khi thiết kế code thu thập kết quả

- **Nguồn có ordered không?** Xác định là `List`, mảng, `LinkedHashSet`, `TreeSet` hay `HashSet/Set.of`.
- **Đầu ra cần giữ thứ tự gì?** Thứ tự nguồn, thứ tự sắp xếp theo khóa hay không cần thứ tự?
- **Cần giữ phần tử trùng không?** `List` giữ trùng; `Set` gom trùng; `distinct()` có thể giữ lần xuất hiện đầu trong ordered stream.
- **Collector nào phù hợp?** `toList()`, `toUnmodifiableList()`, `toCollection(ArrayList::new)`, `toSet()`, `toCollection(LinkedHashSet::new)`.
- **Kết quả cần mutable không?** Ghi rõ nhu cầu thay vì suy đoán implementation của `Collectors.toList()`.
- **Có dùng parallel không?** Tách bảo đảm thứ tự **kết quả** khỏi thứ tự **thực thi callback**.
- **Có `unordered()` không?** Nếu có, kiểm tra lại mọi logic “đầu tiên”, `distinct`, `limit` và display order.
- **Có xử lý null không?** `Stream.toList()` và `Collectors.toUnmodifiableList()` khác nhau về null.
- **Thứ tự có ổn định giữa các lần chạy không?** Nếu nguồn unordered mà cần xuất cố định, sắp xếp theo comparator có tie-breaker.
- **Có test đúng hợp đồng không?** So sánh thứ tự list từ ordered source; đừng kiểm tra thứ tự duyệt của một `HashSet` hoặc `toSet()` không có cam kết.

## 16. Tài liệu chính thức đang áp dụng

- [Java SE API — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): stream encounter order, `sorted`, `distinct`, `unordered`, `parallel`, `forEachOrdered` và `toList`.
- [Java SE API — `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `toUnmodifiableList`, `toCollection`, `toSet` và `toUnmodifiableSet`.
- [Java SE API — `List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): thứ tự list, phần tử trùng và `copyOf`.
- [Java SE API — `Set`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): tính duy nhất, tính không xác định về thứ tự của một số factory set.
- [Java SE API — `LinkedHashSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashSet.html): thứ tự duyệt, phép thêm và tính duy nhất.
- [Java SE API — `HashSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html): không bảo đảm iteration order.
- [Java SE API — `Spliterator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html): đặc tính `ORDERED` của nguồn duyệt.
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi `var` từ Java 10, không thay đổi thứ tự stream hay chính sách collector.

**Ghi nhớ cuối cùng:** Với một **ordered stream**, gom thành danh sách bằng `Collectors.toList()`, `Collectors.toUnmodifiableList()` hoặc `Stream.toList()` duy trì **encounter order**, cả ở pipeline song song khi vẫn giữ ràng buộc thứ tự. `Set` và `Collectors.toSet()` không có cam kết thứ tự hiển thị; nếu cần tập không trùng nhưng nhớ lần xuất hiện đầu tiên, hãy chọn `LinkedHashSet`, còn nếu cần danh sách duy nhất theo lần gặp đầu, hãy cân nhắc `distinct().toList()`.