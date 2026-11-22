# Phân biệt `copyOf` với các phương thức `of` của Collection chỉ đọc trong Java

## Mục tiêu bài học

Java có các factory method để tạo collection **không cho sửa (unmodifiable)**. `List.of`, `Set.of`, `Map.of`, `Map.ofEntries` được hỗ trợ từ Java 9; `List.copyOf`, `Set.copyOf`, `Map.copyOf` được hỗ trợ từ Java 10. Tất cả vẫn là API đang được sử dụng trong Java hiện đại.

Sau bài này, bạn sẽ biết:

- Chọn `of` khi cần tạo collection từ các giá trị trực tiếp, và `copyOf` khi đã có nguồn `Collection`/`Map`.
- Hiểu snapshot của `copyOf` khác view theo dõi nguồn như `Collections.unmodifiableList`.
- So sánh cách xử lý phần tử trùng, khóa trùng, `null`, thứ tự duyệt và giới hạn tham số.
- Giải thích vì sao collection không cho sửa vẫn có thể chứa **đối tượng thay đổi được**, và vì sao `copyOf` không phải deep copy.
- Viết và kiểm tra chương trình Java 17+ có kết quả xác định.

## 1. Điểm chung: kết quả không cho sửa

~~~java
var names = List.of("An", "Binh");
var roles = Set.of("USER", "ADMIN");
var scores = Map.of("An", 9, "Binh", 8);
~~~

Các kết quả trên không hỗ trợ thao tác làm thay đổi cấu trúc hoặc ánh xạ. Những lời gọi như `names.add("Chi")`, `roles.remove("USER")` hoặc `scores.put("Chi", 10)` sẽ ném `UnsupportedOperationException`.

Nhóm `copyOf` cũng trả về collection không cho sửa. Điểm khác biệt chính nằm ở cách cung cấp dữ liệu:

- **`of(...)`** nhận trực tiếp các giá trị tạo thành collection mới.
- **`copyOf(source)`** nhận một collection/map **đã có** và tạo kết quả chứa các phần tử/ánh xạ tương ứng tại thời điểm gọi. Thay đổi cấu trúc nguồn về sau không làm kết quả phản ánh thay đổi ấy.

Không nên gọi các collection này là bất biến sâu: phần tử bên trong vẫn có thể là đối tượng mutable.

## 2. Bảng đối chiếu `of` và `copyOf`

| Tiêu chí | `List/Set/Map.of` | `List/Set/Map.copyOf` |
| --- | --- | --- |
| Nguồn dữ liệu | Các phần tử hoặc cặp khóa/giá trị truyền trực tiếp | Một `Collection` (List/Set) hoặc `Map` có sẵn |
| Kiểu trả về | `List<E>`, `Set<E>`, `Map<K,V>` | `List<E>`, `Set<E>`, `Map<K,V>` |
| Khả năng sửa kết quả | Không cho sửa | Không cho sửa |
| Thay đổi cấu trúc nguồn về sau | Không có collection nguồn được truyền trực tiếp | Không phản ánh các thay đổi ấy |
| Phần tử/khóa/giá trị `null` | Từ chối | Từ chối, kể cả nguồn `null` |
| Phần tử trùng trong List | Cho phép | Cho phép |
| Phần tử trùng trong Set | `Set.of` ném `IllegalArgumentException` | `Set.copyOf` loại trùng, không ném lỗi chỉ vì trùng |
| Khóa trùng trong Map | `Map.of`/`Map.ofEntries` ném `IllegalArgumentException` | Nguồn là `Map` nên vốn không có khóa trùng |
| Thứ tự | List theo thứ tự đối số; Set/Map không bảo đảm thứ tự duyệt | List theo thứ tự duyệt nguồn; Set/Map không bảo đảm thứ tự duyệt |

Với map có **hơn mười cặp** cố định, sử dụng `Map.ofEntries(Map.entry(...), ...)`. `Map.of` có các overload cho tối đa mười cặp. Trong khi đó, `List.of` và `Set.of` có dạng varargs hỗ trợ nhiều phần tử.

## 3. `List.of` và `List.copyOf`

### 3.1. Tạo danh sách trực tiếp bằng `of`

~~~java
var languages = List.of("Java", "Kotlin", "Go");
System.out.println(languages); // [Java, Kotlin, Go]

var repeated = List.of("A", "A", "B");
System.out.println(repeated.size()); // 3
~~~

`List.of` giữ nguyên thứ tự các đối số và **cho phép trùng phần tử**. Nó không chấp nhận `null`:

~~~java
// List.of("A", null); // Ném NullPointerException khi chạy
~~~

Dùng `List.of` cho danh sách giá trị cố định đã biết ngay tại nơi tạo.

### 3.2. Sao chép từ collection hiện có bằng `copyOf`

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var snapshot = List.copyOf(source);

source.add("C");

System.out.println(source);   // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

`List.copyOf(Collection<? extends E>)` trả về `List<E>` không cho sửa, chứa phần tử theo **thứ tự duyệt nguồn ở thời điểm gọi**. Nếu nguồn là một `Set` không có thứ tự duyệt được cam kết, bản sao dạng List cũng không tự bảo đảm một thứ tự cụ thể.

Đây là cách phù hợp để tạo danh sách snapshot trước khi trao kết quả cho mã khác.

### 3.3. Phân biệt snapshot với unmodifiable view

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var snapshot = List.copyOf(source);
var view = Collections.unmodifiableList(source);

source.add("C");

System.out.println(snapshot); // [A, B]
System.out.println(view);     // [A, B, C]
~~~

Cả `snapshot` và `view` đều từ chối thao tác sửa thông qua chính chúng. Nhưng `Collections.unmodifiableList(source)` tạo **view** tham chiếu tới nguồn: nếu mã khác sửa `source`, view vẫn thấy dữ liệu mới. `List.copyOf` trả về snapshot, không phản ánh những thay đổi cấu trúc ấy.

`Collections.unmodifiableList` vẫn là API hợp lệ và có ích nếu thực sự cần view không cho sửa nhưng luôn quan sát nguồn. Chọn theo yêu cầu, không coi một API là đã lỗi thời.

## 4. `Set.of` và `Set.copyOf`: khác biệt về phần tử trùng

~~~java
var colors = Set.of("red", "blue");
// Set.of("red", "red"); // Ném IllegalArgumentException
~~~

`Set.of` kiểm tra phần tử trùng tại lúc tạo. Nếu hai đối số được xem là bằng nhau theo `equals`, factory ném `IllegalArgumentException`; nhờ đó có thể phát hiện cấu hình bị trùng.

`Set.copyOf` lại nhận một **`Collection`**, kể cả `List` có phần tử trùng:

~~~java
var input = List.of("red", "red", "blue");
var colors = Set.copyOf(input);
System.out.println(colors.size()); // 2
~~~

Nó giữ một đại diện cho mỗi giá trị duy nhất mà không ném lỗi vì nguồn có phần tử trùng. Khi các đối tượng khác nhau nhưng `equals` trả `true`, Java **không bảo đảm giữ tham chiếu đầu tiên hay cuối cùng**; có thể giữ một đại diện bất kỳ.

Cả `Set.of` và `Set.copyOf` đều **không cam kết thứ tự duyệt**. Nếu cần hiển thị có thứ tự, hãy sắp xếp rõ ràng thay vì dựa vào thứ tự in ra từ Set.

## 5. `Map.of`, `Map.ofEntries` và `Map.copyOf`

### 5.1. Tạo Map trực tiếp

~~~java
var config = Map.of("read", 10, "write", 5);

var prices = Map.ofEntries(
    Map.entry("book", 100),
    Map.entry("pen", 20),
    Map.entry("notebook", 50)
);
~~~

`Map.of` là lựa chọn gọn với số cặp nhỏ. `Map.ofEntries` phù hợp với danh sách cặp lớn hơn; có thể truyền nhiều `Map.entry(k, v)` vào cùng lời gọi.

Cả hai đều từ chối khóa/giá trị `null`, và sẽ ném `IllegalArgumentException` khi bạn khai báo khóa trùng:

~~~java
// Map.of("A", 1, "A", 2); // Ném IllegalArgumentException
~~~

Thứ tự duyệt cặp ánh xạ của hai factory này không được bảo đảm.

### 5.2. Sao chép Map hiện có

~~~java
var source = new LinkedHashMap<String, Integer>();
source.put("An", 9);

var snapshot = Map.copyOf(source);
source.put("Binh", 8);

System.out.println(snapshot.size());    // 1
System.out.println(snapshot.get("An")); // 9
~~~

`Map.copyOf` nhận `Map<? extends K, ? extends V>` và tạo kết quả không cho sửa với các ánh xạ tại thời điểm gọi. Việc thêm, xóa hoặc gán lại giá trị trong map nguồn về sau không cập nhật ánh xạ của snapshot.

Một `Map` hợp lệ đã bảo đảm khóa duy nhất, nên đầu vào `Map.copyOf` không có tình huống chứa hai entry mang cùng một khóa theo hợp đồng Map. Ngược lại, khi liệt kê cặp trực tiếp qua `Map.of`/`Map.ofEntries`, Java phải kiểm tra trùng khóa.

`Map.copyOf` cũng **không cam kết giữ thứ tự duyệt** của `LinkedHashMap` nguồn. Nếu nguồn chứa khóa hoặc giá trị `null`, nó ném `NullPointerException`.

## 6. Chương trình Java 17+ chạy độc lập

Lưu mã sau vào tệp **CopyOfVsOfDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CopyOfVsOfDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        var direct = List.of("An", "Binh");

        var source = new ArrayList<>(List.of("An", "Binh"));
        var snapshot = List.copyOf(source);
        var view = Collections.unmodifiableList(source);
        source.add("Chi");

        System.out.println("List.of: " + direct);
        System.out.println("List.copyOf: " + snapshot);
        System.out.println("List view: " + view);
        System.out.println("List.of duplicates: " + List.of("A", "A").size());

        var fromDuplicates = Set.copyOf(List.of("A", "A", "B"));
        System.out.println("Set.copyOf size: " + fromDuplicates.size());

        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException e) {
            System.out.println("Set.of duplicate: IllegalArgumentException");
        }

        var mapSource = new LinkedHashMap<String, Integer>();
        mapSource.put("a", 1);
        var mapCopy = Map.copyOf(mapSource);
        mapSource.put("b", 2);

        System.out.println("Map.copyOf a: " + mapCopy.get("a"));
        System.out.println("Map.copyOf size: " + mapCopy.size());
        System.out.println("Map.of size: " + Map.of("x", 10).size());

        try {
            Map.of("x", 1, "x", 2);
        } catch (IllegalArgumentException e) {
            System.out.println("Map.of duplicate key: IllegalArgumentException");
        }

        try {
            List.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException e) {
            System.out.println("List.copyOf null: NullPointerException");
        }

        var box = new Box(1);
        var boxes = List.copyOf(List.of(box));
        box.value = 99;
        System.out.println("Mutable element: " + boxes.get(0).value);
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn, tại thư mục chứa file:

~~~bash
javac CopyOfVsOfDemo.java
java CopyOfVsOfDemo
~~~

Kết quả chính xác:

~~~text
List.of: [An, Binh]
List.copyOf: [An, Binh]
List view: [An, Binh, Chi]
List.of duplicates: 2
Set.copyOf size: 2
Set.of duplicate: IllegalArgumentException
Map.copyOf a: 1
Map.copyOf size: 1
Map.of size: 1
Map.of duplicate key: IllegalArgumentException
List.copyOf null: NullPointerException
Mutable element: 99
~~~

Ví dụ chỉ in `size()` và truy vấn `get(key)` cho Set/Map, do đó **không phụ thuộc thứ tự duyệt không được cam kết**. Các nhánh `catch` in loại lỗi, tránh phụ thuộc nội dung message do implementation tạo ra.

Những điều cần quan sát:

1. `List.of` tạo danh sách trực tiếp từ hai chuỗi.
2. `List.copyOf` vẫn có `[An, Binh]` dù nguồn đã thêm `"Chi"`; view thì thấy cả ba phần tử.
3. `List.of` giữ phần tử trùng, `Set.copyOf` loại trùng, còn `Set.of` ném lỗi.
4. `Map.copyOf` giữ snapshot một ánh xạ sau khi map nguồn được thêm phần tử.
5. `List.copyOf` không nhận phần tử `null`.
6. Thay đổi trạng thái đối tượng `Box` vẫn quan sát được qua collection `boxes`.

## 7. Snapshot không phải deep copy

`copyOf` tạo snapshot về **các phần tử/ánh xạ của collection**; nó không tự tạo một bản sao sâu của từng object được tham chiếu. Phần tử có thể thay đổi trạng thái sau khi copy.

~~~java
// Đoạn mã minh họa nằm trong một phương thức:
var builder = new StringBuilder("old");
var input = new ArrayList<StringBuilder>();
input.add(builder);

var result = List.copyOf(input);
builder.append("-new");

System.out.println(result.get(0)); // old-new
~~~

Tuy `result.add(...)` không được hỗ trợ, `StringBuilder` được tham chiếu vẫn mutable, và code bên ngoài vẫn có thể sửa nó. Điều tương tự xảy ra với object làm value trong `Map.copyOf`. Key mutable còn có thể gây lỗi tra cứu nếu các thuộc tính tham gia `equals`/`hashCode` bị thay đổi.

Khi cần bất biến thực sự ở tầng nghiệp vụ, hãy sử dụng **value object bất biến**, hoặc chủ động sao chép trạng thái của phần tử trước khi đóng gói collection.

## 8. `copyOf` có thể tái sử dụng instance đã không cho sửa

Tên `copyOf` không cam kết cấp phát một object mới mỗi lần gọi:

~~~java
var original = List.of("A", "B");
var copied = List.copyOf(original);
~~~

Nếu nguồn đã là collection không cho sửa phù hợp, implementation có thể trả lại cùng instance. **Không dùng `original == copied` như phép kiểm tra bản sao đúng hay sai**; nên so sánh nội dung theo `equals` khi cần. Những kết quả factory thuộc dạng *value-based*: không viết logic phụ thuộc vào danh tính đối tượng của chúng hoặc dùng chúng làm khóa đồng bộ hóa.

Cam kết quan trọng là nội dung cấu trúc được bảo vệ trước thay đổi ở nguồn, không phải việc cấp phát một instance mới.

## 9. Kiểm tra `null` đúng cách

Cả hai nhóm đều không cho phần tử `null`; `Map` không cho khóa hoặc value `null`:

~~~java
// Tất cả dòng dưới đây đều gây NullPointerException khi chạy:
// List.of("A", null);
// Set.of("A", null);
// Map.of("A", null);
~~~

Nguồn `ArrayList` có thể chứa `null`, nhưng khi gọi `List.copyOf(source)` sẽ ném `NullPointerException`. Tương tự, `Set.copyOf` với collection chứa `null`, hoặc `Map.copyOf` với map có key/value `null`, đều không hợp lệ. Truyền nguồn `null` trực tiếp cũng không hợp lệ.

Nếu đầu vào có dữ liệu thiếu, hãy xử lý theo quy tắc nghiệp vụ trước khi tạo kết quả: lọc phần tử không hợp lệ khi được phép, dùng kiểu mô tả trạng thái thiếu dữ liệu hoặc báo lỗi rõ ràng. Không nên âm thầm thay `null` bằng giá trị giả chỉ để factory chạy.

## 10. Thứ tự duyệt và phần tử trùng

| Factory | Thứ tự duyệt | Phần tử/khóa trùng |
| --- | --- | --- |
| `List.of` | Theo thứ tự đối số | Được phép |
| `List.copyOf` | Theo thứ tự duyệt nguồn lúc gọi | Được phép |
| `Set.of` | Không được cam kết | Ném `IllegalArgumentException` |
| `Set.copyOf` | Không được cam kết | Chỉ giữ một đại diện bất kỳ |
| `Map.of`/`Map.ofEntries` | Không được cam kết | Khóa trùng gây `IllegalArgumentException` |
| `Map.copyOf` | Không được cam kết | Nguồn Map có khóa duy nhất theo hợp đồng |

Đối với code dùng kết quả của `Set.of` hoặc `Map.copyOf`, hãy tránh thử nghiệm kiểu `toString().equals("{A=1, B=2}")`, vì thứ tự có thể khác giữa các lần chạy. Khi cần tính toán dựa trên thứ tự, tạo thứ tự theo quy tắc nghiệp vụ và kiểm tra nó tường minh.

## 11. Dùng generic và `var` khi tạo collection chỉ đọc

Các factory trên đều là generic. Khi nguồn biểu lộ kiểu, `var` giữ được kiểu phù hợp:

~~~java
var names = List.of("An", "Binh");      // List<String>
var copy = List.copyOf(names);         // List<String>
var uniqueNames = Set.copyOf(names);   // Set<String>
~~~

Tuy nhiên, factory rỗng không có dữ liệu để suy luận kiểu phần tử nếu dùng `var`:

~~~java
var unknown = List.of();               // List<Object>
var known = List.<String>of();         // List<String>
List<String> alsoKnown = List.of();    // List<String> nhờ kiểu đích
~~~

Bạn có thể dùng **type witness** như `List.<String>of()`, `Set.<String>of()`, `Map.<String, Integer>of()` khi muốn giữ `var` và cần xác định rõ kiểu generic.

Với `copyOf`, kiểu suy luận đến từ collection/map nguồn. Hãy giữ khai báo generic của nguồn chính xác và cân nhắc viết kiểu biến tường minh khi nó giúp truyền đạt hợp đồng API tốt hơn.

## 12. Khi nào chọn API nào?

| Nhu cầu | Lựa chọn gợi ý | Vì sao |
| --- | --- | --- |
| Danh sách các literal có thứ tự | `List.of(...)` | Gọn và giữ thứ tự đối số |
| Một tập hằng cấu hình cần phát hiện trùng | `Set.of(...)` | Báo lỗi nếu khai báo trùng |
| Một map nhỏ với các cặp cố định | `Map.of(...)` | Truyền trực tiếp cặp khóa/giá trị |
| Map có hơn 10 cặp cố định | `Map.ofEntries(...)` | Hỗ trợ số lượng entry lớn |
| Nhận một `List` mutable và cần snapshot | `List.copyOf(list)` | Không phụ thuộc biến động cấu trúc nguồn |
| Nhận một collection có giá trị trùng, chỉ muốn giá trị duy nhất | `Set.copyOf(collection)` | Loại trùng, không cam kết thứ tự |
| Nhận một map mutable và cần snapshot | `Map.copyOf(map)` | Giữ ánh xạ tại thời điểm gọi |
| Muốn read-only view luôn thấy thay đổi của nguồn | `Collections.unmodifiableList(list)` | Có chủ đích theo dõi collection gốc |
| Muốn collection có thể thay đổi được | `new ArrayList<>(list)`, `new HashMap<>(map)` | Các constructor này tạo collection sửa được |

Không nên gọi `List.copyOf` một cách tự động khi chỉ cần `List.of` từ các giá trị đã biết. Cũng không nên gọi `List.of(source)` để tạo một snapshot **các phần tử** của `Collection`: nếu `source` là một List và bạn truyền như một đối số đơn, kết quả là List chứa chính List đó như **một phần tử**. Dùng `List.copyOf(source)` khi mục đích là sao chép các phần tử của collection nguồn.

## 13. Các lỗi thường gặp

**Lỗi A — nhầm `Set.copyOf` và `Set.of` khi trùng:** `Set.copyOf(List.of("x","x"))` có một phần tử; `Set.of("x","x")` ném `IllegalArgumentException`. Nếu trùng là lỗi dữ liệu, phải phát hiện rõ trước khi copy.

**Lỗi B — nhầm snapshot với view:** `Collections.unmodifiableList(source)` phản ánh thay đổi của source, còn `List.copyOf(source)` không phản ánh thay đổi cấu trúc của source sau thời điểm gọi.

**Lỗi C — nghĩ `final` đủ làm collection không cho sửa:**

~~~java
final List<String> list = new ArrayList<>();
list.add("A"); // Hợp lệ: final chỉ chặn gán lại biến list.
~~~

`final` kiểm soát việc gán lại biến tham chiếu, còn `List.copyOf` kiểm soát khả năng sửa **kết quả collection**.

**Lỗi D — nghĩ `copyOf` deep clone:** đối tượng bên trong có thể mutable; snapshot không tự đóng băng trạng thái của từng object.

**Lỗi E — phụ thuộc thứ tự của Set hoặc Map:** các factory này không bảo đảm thứ tự duyệt; kiểm tra `size`, `contains`, `get`, hoặc sắp xếp khi cần thứ tự.

**Lỗi F — nghĩ có thể giữ `null`:** cả `of` và `copyOf` đều từ chối phần tử/khóa/value `null`.

**Lỗi G — nghĩ `copyOf` luôn tạo object khác:** có thể tái sử dụng nguồn đã không cho sửa; không dựa vào `==`.

## 14. Tự kiểm tra

Hãy dự đoán kết quả trước khi xem đáp án:

~~~java
var source = new ArrayList<>(List.of("A", "B", "A"));
var list = List.copyOf(source);
var set = Set.copyOf(source);

source.add("C");

// list.size() sẽ là bao nhiêu?
// set.size() sẽ là bao nhiêu?
// list.contains("C") là true hay false?
// Set.of("A", "A") trả về Set hay ném lỗi?
// Có thể chắc chắn Set.copyOf duyệt theo thứ tự "A", "B" không?
~~~

**Đáp án:** `list.size()` bằng 3 vì List giữ cả phần tử trùng; `set.size()` bằng 2 vì Set loại giá trị trùng; `list.contains("C")` là `false` do thay đổi nguồn xảy ra sau `copyOf`; `Set.of("A", "A")` ném `IllegalArgumentException`; và không có bảo đảm duyệt Set theo thứ tự `A`, `B`.

## 15. Ghi nhớ và tài liệu chuẩn

- **`of`**: tạo trực tiếp collection không cho sửa từ những giá trị truyền vào.
- **`copyOf`**: tạo kết quả không cho sửa từ collection/map có sẵn; thay đổi cấu trúc nguồn về sau không lan sang kết quả.
- **List** giữ thứ tự và cho phép trùng. **Set** loại trùng nhưng `Set.of` báo lỗi khi khai báo trùng. **Map** có khóa duy nhất và `Map.of`/`ofEntries` báo lỗi nếu khai báo trùng khóa.
- Cả hai nhóm đều từ chối `null`, không tạo deep copy, và có thể tái sử dụng đối tượng không cho sửa trong trường hợp phù hợp.
- Thứ tự duyệt của `Set.of`, `Set.copyOf`, `Map.of`, `Map.ofEntries` và `Map.copyOf` không được cam kết.

Tài liệu Java SE 17 (API còn được hỗ trợ trên các JDK hiện hành):

- [`List`: `of` và `copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
- [`Set`: `of` và `copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [`Map`: `of`, `ofEntries`, `copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [`Collection`: Unmodifiable Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

**Kết luận:** Chọn `of` khi biết sẵn từng giá trị và chọn `copyOf` khi muốn tạo collection chỉ đọc từ nguồn hiện có. Khi thiết kế API, hãy xét rõ phần tử trùng, `null`, thứ tự duyệt, snapshot so với view và trạng thái mutable của phần tử được chứa.
