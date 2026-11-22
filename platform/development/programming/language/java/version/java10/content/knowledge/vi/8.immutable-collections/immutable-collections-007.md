# Quy tắc `null` tại ranh giới tạo collection chỉ đọc trong Java

*Ngữ cảnh: Java 10 — Collection chỉ đọc. Bài học tập trung vào các API và quy tắc vẫn áp dụng cho Java 17+ và các bản Java hiện đại. Trong Java, “unmodifiable collection”, “read-only view” và “immutable object” không đồng nghĩa tuyệt đối.*

## 1. Kết luận quan trọng nhất

Khi công khai một collection không cho phép người nhận sửa qua giao diện của nó, hãy coi việc **kiểm tra `null` là một phần của hợp đồng dữ liệu ngay tại ranh giới tạo collection**. Các factory và phương thức sao chép hiện đại thường dùng để xuất bản collection không thể sửa **không chấp nhận `null`**:

~~~java
var names = List.of("An", "Binh");                // Không có null
var roles = Set.of("reader", "writer");           // Không có null
var scores = Map.of("An", 9, "Binh", 8);          // Không có null ở key/value
var publishedNames = List.copyOf(names);        // Không có null
var publishedRoles = Set.copyOf(roles);         // Không có null
var publishedScores = Map.copyOf(scores);       // Không có null ở key/value
~~~

**Cần nhớ ba nhóm quy tắc:**

1. `List.of(...)`, `Set.of(...)`, `Map.of(...)`, `Map.ofEntries(...)` tạo collection không thể sửa và **từ chối phần tử `null`**; riêng `Map` từ chối cả **khóa** và **giá trị** `null`. Chúng xuất hiện từ Java 9 và vẫn được hỗ trợ hiện nay.
2. `List.copyOf(...)`, `Set.copyOf(...)`, `Map.copyOf(...)` (Java 10) tạo ra kết quả không thể sửa và **từ chối đầu vào `null` hoặc dữ liệu bên trong có `null`** theo từng loại collection.
3. `Collections.unmodifiableList(...)`, `Collections.unmodifiableSet(...)`, `Collections.unmodifiableMap(...)` là **view không thể sửa qua view**, có thể hiển thị phần tử/khóa/giá trị `null` nếu collection nền chứa chúng. Bản thân việc bọc view **không đồng nghĩa với xác thực dữ liệu không-null**.

Quy tắc này vẫn áp dụng khi dùng `var`. Suy luận kiểu cục bộ không thay đổi hành vi kiểm tra `null` của API.

## 2. “Ranh giới tạo collection” là gì?

Trong một ứng dụng, dữ liệu thường đi qua các chặng:

~~~text
API / database / cấu hình / request bên ngoài
                |
                v
      Collection đầu vào (có thể chứa null)
                |
                v
      Kiểm tra và chuẩn hóa theo hợp đồng
                |
                v
 List.copyOf / Set.copyOf / Map.copyOf
                |
                v
  Collection xuất bản cho mã sử dụng nội bộ
~~~

Một biến `List<String>` hoặc `Map<String,Integer>` **không có bảo đảm non-null chỉ nhờ tham số generic**. Java cho phép một số lớp triển khai chứa `null`, ví dụ `ArrayList` và `HashMap`. Vì thế, ranh giới từ dữ liệu bên ngoài sang trạng thái được xem là đã hợp lệ là vị trí thích hợp để:

- Xác định `null` có phải dữ liệu không hợp lệ, giá trị thiếu có ý nghĩa hay một phần tử được phép hay không.
- Chọn một chính sách: **từ chối**, **bỏ phần tử null có chủ đích**, hoặc **mô hình hóa trạng thái thiếu bằng kiểu khác**.
- Tạo collection không thể sửa bằng API có hợp đồng phù hợp.
- Giữ lỗi ở gần nguồn dữ liệu, thay vì để một lời gọi ở xa nhận `NullPointerException` khó chẩn đoán.

Ví dụ đầu vào danh sách tên:

~~~java
var incoming = new ArrayList<String>();
incoming.add("An");
incoming.add(null);
incoming.add("Binh");
~~~

Đây là một `ArrayList<String>` **hợp lệ**, nhưng chưa phù hợp hợp đồng `List.copyOf`. Khi tạo snapshot:

~~~java
// Dòng sau sẽ ném NullPointerException ở runtime:
var published = List.copyOf(incoming);
~~~

Điều đó không phải lỗi của `var` hay generics; chính phương thức `List.copyOf` yêu cầu nguồn và từng phần tử không phải `null`.

## 3. Bảng các API thường gặp và chính sách `null`

| API tạo/bao collection | Chấp nhận `null` ở dữ liệu được chứa? | Kết quả và lưu ý |
| --- | --- | --- |
| `List.of("a", null)` | **Không** | Ném `NullPointerException` |
| `Set.of("a", null)` | **Không** | Ném `NullPointerException` |
| `Map.of("a", null)` | **Không** | Ném `NullPointerException` do value |
| `Map.of(null, 1)` | **Không** | Ném `NullPointerException` do key |
| `Map.entry("a", null)` | **Không** | Ném `NullPointerException` khi tạo entry |
| `Map.ofEntries(...)` | **Không** | Không chấp nhận entry/key/value `null` |
| `List.copyOf(source)` | **Không** | Nguồn hoặc phần tử `null` gây `NullPointerException` |
| `Set.copyOf(source)` | **Không** | Nguồn hoặc phần tử `null` gây `NullPointerException` |
| `Map.copyOf(source)` | **Không** | Nguồn/key/value `null` gây `NullPointerException` |
| `Collections.unmodifiableList(source)` | **Có thể có** | View phản ánh dữ liệu của collection nền; không lọc `null` |
| `Collections.unmodifiableSet(source)` | **Có thể có** | Tùy collection nền có cho phép `null` hay không |
| `Collections.unmodifiableMap(source)` | **Có thể có** | View có thể hiển thị key/value `null` của map nền |
| `Stream.toList()` (Java 16+) | **Có thể có** | Trả danh sách không thể sửa, nhưng không áp đặt chính sách cấm `null` như `List.copyOf` |
| `Collectors.toUnmodifiableList()` (Java 10+) | **Không** | Ném `NullPointerException` khi phần tử stream là `null` |
| `Collectors.toUnmodifiableSet()` (Java 10+) | **Không** | Ném `NullPointerException` nếu gặp `null` |
| `Collectors.toUnmodifiableMap(...)` (Java 10+) | **Không** | Ném `NullPointerException` nếu key mapper hoặc value mapper cho ra `null` |

Ở đây, “có thể có” nghĩa là **không tự loại trừ `null` ở ranh giới này**, chứ không có nghĩa mọi triển khai đều nhận `null`. Với `HashSet` và `HashMap`, `null` có thể được lưu theo các quy tắc tương ứng; các triển khai khác có thể có giới hạn riêng.

**Lưu ý:** `List.of(...)`, `Set.of(...)` và `Map.of(...)` còn có những giới hạn riêng không liên quan trực tiếp tới `null`: `Set.of` không cho phần tử trùng, `Map.of` không cho khóa trùng. `Set.copyOf` có thể loại các phần tử trùng trong nguồn theo hợp đồng tạo set. Không suy diễn các quy tắc trùng lặp từ quy tắc `null`.

## 4. Ví dụ hoàn chỉnh: xử lý `null` trước khi xuất bản

Chương trình dưới đây biên dịch với Java 17+ và chỉ dùng thư viện JDK. Nó chứng minh các trường hợp `null` ở `List`, `Set`, `Map`, sự khác biệt giữa snapshot và read-only view, và hai cách gom stream.

~~~java
// File: CollectionNullBoundaryDemo.java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionNullBoundaryDemo {
    public static void main(String[] args) {
        var input = new ArrayList<>(Arrays.asList("An", null, "Binh"));
        try {
            List.copyOf(input);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("List.copyOf rejects null = true");
        }

        var cleaned = input.stream()
                .filter(Objects::nonNull)
                .toList();
        var published = List.copyOf(cleaned);
        input.set(0, "Changed");
        System.out.println("published = " + published);
        System.out.println("cleaned = " + cleaned);

        var backing = new ArrayList<String>();
        backing.add(null);
        var view = Collections.unmodifiableList(backing);
        backing.add("X");
        System.out.println("view = " + view);

        var streamList = Stream.<String>of("An", null).toList();
        System.out.println("Stream.toList accepts null = "
                + (streamList.get(1) == null));
        try {
            Stream.<String>of("An", null)
                    .collect(Collectors.toUnmodifiableList());
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("toUnmodifiableList rejects null = true");
        }

        try {
            List.of("An", null);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("List.of rejects null = true");
        }
        try {
            Set.of("An", null);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("Set.of rejects null = true");
        }
        try {
            Map.of("a", null);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("Map.of rejects null value = true");
        }
        try {
            Map.of(null, 1);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("Map.of rejects null key = true");
        }

        var source = new HashMap<String, Integer>();
        source.put("a", 1);
        source.put("b", null);
        try {
            Map.copyOf(source);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("Map.copyOf rejects null value = true");
        }
        source.remove("b");
        var publishedMap = Map.copyOf(source);
        source.put("c", 3);
        System.out.println("published map size = " + publishedMap.size());

        var ids = Set.copyOf(List.of(1, 1, 2));
        System.out.println("Set.copyOf unique size = " + ids.size());
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac --release 17 CollectionNullBoundaryDemo.java
java CollectionNullBoundaryDemo
~~~

Stdout chính xác:

~~~text
List.copyOf rejects null = true
published = [An, Binh]
cleaned = [An, Binh]
view = [null, X]
Stream.toList accepts null = true
toUnmodifiableList rejects null = true
List.of rejects null = true
Set.of rejects null = true
Map.of rejects null value = true
Map.of rejects null key = true
Map.copyOf rejects null value = true
published map size = 1
Set.copyOf unique size = 2
~~~

**Phân tích kỹ kết quả:**

1. `List.copyOf(input)` ném `NullPointerException` do `input` có một phần tử `null`. Bài kiểm tra bắt ngoại lệ **đúng loại**, không phụ thuộc văn bản thông báo cụ thể của JVM.
2. `filter(Objects::nonNull)` loại phần tử null một cách **có chủ đích**. `toList()` tạo `List<String>` không thể sửa chứa `An`, `Binh`; `List.copyOf(cleaned)` xuất bản kết quả null-free.
3. Sau khi `input.set(0, "Changed")`, `published` vẫn là `[An, Binh]`: snapshot từ `List.copyOf` không phản ánh các thay đổi cấu trúc/ánh xạ phần tử sau đó của collection đầu vào.
4. `Collections.unmodifiableList(backing)` tạo **view**; việc `backing.add("X")` làm `view` hiển thị `[null, X]`. Vậy view có thể không thể sửa từ phía người dùng nhưng vẫn **chứa null** và **thấy thay đổi ở nguồn**.
5. `Stream.toList()` tạo danh sách không thể sửa nhưng không thực hiện chính sách từ chối null giống `Collectors.toUnmodifiableList()`. Kết quả trong thử nghiệm cho thấy phần tử thứ hai vẫn là null.
6. `List.of`, `Set.of` và `Map.of` đều ném ngoại lệ ngay tại ranh giới factory khi gặp null tương ứng.
7. `Map.copyOf(source)` từ chối map chứa null value. Sau khi xóa entry đó, kết quả có kích thước 1 và không thay đổi khi map nguồn được thêm entry mới.
8. `Set.copyOf(List.of(1, 1, 2))` trả một set có hai phần tử khác nhau. Chương trình **không in thứ tự** duyệt set, vì thứ tự không được cam kết.

## 5. Ba chính sách xử lý dữ liệu có `null`

### 5.1. Chính sách A — từ chối đầu vào sai hợp đồng (fail fast)

Đây thường là lựa chọn phù hợp khi `null` thể hiện dữ liệu hỏng hoặc trường bắt buộc bị thiếu. Để lỗi xuất hiện gần nơi nhận đầu vào thay vì để nó tiếp tục đi sâu vào hệ thống.

~~~java
static List<String> publishNames(List<String> input) {
    Objects.requireNonNull(input, "input must not be null");
    return List.copyOf(input); // NPE nếu có bất kỳ phần tử null nào
}
~~~

Đoạn trên là **phương thức để đặt trong một lớp**, với import `java.util.List` và `java.util.Objects`. Nó có thể biên dịch trên Java 17+.

Trong ứng dụng cần chẩn đoán chính xác phần tử lỗi, kiểm tra chỉ số trước khi sao chép:

~~~java
static List<String> requireNames(List<String> input) {
    Objects.requireNonNull(input, "input");
    for (int i = 0; i < input.size(); i++) {
        if (input.get(i) == null) {
            throw new IllegalArgumentException("Name missing at index " + i);
        }
    }
    return List.copyOf(input);
}
~~~

Cách này làm thông báo lỗi có ý nghĩa nghiệp vụ hơn. Tuy nhiên, nếu collection đầu vào có thể bị luồng khác sửa đồng thời, vòng kiểm tra và sao chép không phải một giao dịch nguyên tử; cần có chiến lược đồng bộ hoặc snapshot phù hợp theo thiết kế hệ thống.

### 5.2. Chính sách B — bỏ null khi null nghĩa là “không có mục hợp lệ”

Chỉ **lọc** khi hợp đồng cho phép bỏ mục bị thiếu, chẳng hạn tập thẻ tùy chọn hoặc danh sách gợi ý không bắt buộc.

~~~java
static List<String> publishNonNullTags(List<String> input) {
    Objects.requireNonNull(input, "input");
    var withoutNulls = input.stream()
            .filter(Objects::nonNull)
            .toList();
    return List.copyOf(withoutNulls);
}
~~~

Việc bỏ phần tử null **thay đổi số phần tử và vị trí**. Nếu đầu vào có 4 mục và mục thứ hai là null, đầu ra chỉ còn 3 mục; chỉ số các mục phía sau dịch sang trái. Đừng lặng lẽ lọc null trong dữ liệu mà số lượng hoặc vị trí có ý nghĩa nghiệp vụ (ví dụ các cột của một bản ghi hay các bước giao dịch).

Với `Set` và `Map`, cần thiết kế tương tự nhưng phải làm rõ quy tắc khóa/value, tính duy nhất và trường hợp thiếu khóa. Ví dụ, có thể từ chối null key vì không xác định được danh tính bản ghi, nhưng bỏ null value nếu đó là quy tắc công khai của ứng dụng.

### 5.3. Chính sách C — mô hình hóa “thiếu dữ liệu” thay vì chèn null

Khi thiếu dữ liệu là tình huống **hợp lệ cần được biểu diễn**, hãy thiết kế hợp đồng rõ ràng. Ví dụ, dùng `Optional` ở ranh giới một giá trị:

~~~java
static java.util.Optional<String> normalizedName(String name) {
    return java.util.Optional.ofNullable(name)
            .map(String::trim)
            .filter(s -> !s.isEmpty());
}
~~~

Hàm này trả `Optional.empty()` nếu đầu vào là null hoặc chỉ gồm khoảng trắng; trả `Optional<String>` có nội dung trong các trường hợp khác. Đây là **ví dụ thiết kế cho một giá trị**, không có nghĩa mọi collection nên lưu hàng loạt đối tượng `Optional` như phần tử.

Khi không có phần tử nào là kết quả bình thường, thay vì trả `null` cho toàn bộ collection có thể trả `List.of()`, `Set.of()` hoặc `Map.of()`:

~~~java
static List<String> findNames(boolean found) {
    return found ? List.of("An") : List.of();
}
~~~

Việc chọn collection rỗng thay vì null chỉ phù hợp khi “không có kết quả” **không cần phân biệt** với trạng thái “chưa tải dữ liệu” hoặc “lỗi”. Nếu cần phân biệt, biểu diễn bằng kiểu kết quả hoặc trạng thái riêng.

## 6. `List.of`, `Set.of` và `Map.of`: lỗi xuất hiện ngay khi tạo

~~~java
// Các dòng sau minh họa lỗi runtime; không chạy chung nếu muốn chương trình tiếp tục.
var badList = List.of("A", null);           // NullPointerException
var badSet = Set.of("A", null);             // NullPointerException
var badValues = Map.of("A", null);         // NullPointerException
var badKeys = Map.of(null, 10);            // NullPointerException
~~~

Phương thức factory không chứa bộ lọc tự động: khi gặp null, nó **từ chối tạo kết quả**. Đây là đặc tính tốt để thực thi hợp đồng “không null”.

Lưu ý dùng `Map.ofEntries`:

~~~java
// Map.entry đã từ chối giá trị null:
var entry = Map.entry("A", null); // NullPointerException
~~~

Không đợi đến `Map.ofEntries(entry)` rồi mới mong kiểm tra được null; `Map.entry` đã có hợp đồng loại trừ null key/value.

### Cảnh báo thêm về lỗi không phải null

~~~java
// Khóa bị lặp, không phải lỗi null:
var duplicateKeys = Map.of("A", 1, "A", 2); // IllegalArgumentException
// Phần tử set bị lặp:
var duplicateItems = Set.of("A", "A");      // IllegalArgumentException
~~~

`Set.copyOf` được phép gom các phần tử lặp thành một phần tử của set. Nếu dữ liệu không được phép chứa bản ghi trùng, hãy kiểm tra điều kiện trùng riêng; `copyOf` **không thay cho mọi validation**.

## 7. `copyOf` không phải chỉ là “bọc collection”

### 7.1. Một snapshot khác read-only view

~~~java
var source = new ArrayList<>(List.of("A"));
var snapshot = List.copyOf(source);
var view = Collections.unmodifiableList(source);

source.add("B");

// snapshot là [A], view là [A, B]
~~~

`List.copyOf(source)` cho ra danh sách không thể sửa, không phản ánh thay đổi xảy ra **sau đó** ở `source`. `Collections.unmodifiableList(source)` cho ra view không thể sửa qua view nhưng vẫn quan sát thay đổi của danh sách nền.

Điểm tương tự áp dụng cho `Set.copyOf`/`Map.copyOf` so với `Collections.unmodifiableSet`/`Collections.unmodifiableMap`. Tuy nhiên, không nên khẳng định `copyOf` **luôn phân bổ đối tượng mới**: Java có thể tái sử dụng một collection đã không thể sửa phù hợp. Chỉ dựa vào **hợp đồng về dữ liệu và khả năng sửa**, không dựa vào danh tính tham chiếu hoặc số lần cấp phát.

### 7.2. Vẫn là bất biến nông (shallow), không phải sao chép sâu

~~~java
var builder = new StringBuilder("A");
var contents = List.of(builder); // List<StringBuilder>, không sửa cấu trúc
builder.append("B");
// contents.get(0).toString() là "AB"
~~~

Danh sách không cho thêm, xóa hay thay thế phần tử nhưng đối tượng `StringBuilder` bên trong vẫn thay đổi được. Vì thế “không thể sửa” ở đây chủ yếu nói về **cấu trúc collection**, không đồng nghĩa toàn bộ object graph là immutable. Nếu cần tính bất biến sâu, chọn giá trị phần tử bất biến hoặc tự sao chép chúng theo hợp đồng.

### 7.3. `null` ở map có hai vị trí độc lập

~~~java
var source = new HashMap<String, Integer>();
source.put(null, 1); // HashMap cho phép một null key
source.put("A", null); // HashMap cho phép null values

// Map.copyOf(source) sẽ ném NullPointerException.
~~~

Ranh giới công khai `Map<K,V>` không thể sửa cần kiểm tra **cả key và value**, không chỉ các phần tử value. Dù chỉ một key hoặc value null, `Map.copyOf` đều từ chối. Nếu cần giữ quan hệ “khóa tồn tại nhưng value vắng mặt”, hãy mô hình hóa trạng thái đó có chủ đích thay vì mặc định map không thể sửa hiện đại vẫn nhận null.

## 8. Những khác biệt dễ nhầm ở Stream và Collector

Điểm này quan trọng vì một collection “không sửa được” **không tự suy ra** “không chứa null”.

~~~java
var fromToList = Stream.<String>of("A", null).toList();
// Có thể chứa null: [A, null], nhưng không thêm/xóa phần tử được.

// Dòng sau ném NullPointerException:
var fromCollector = Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableList());
~~~

`Stream.toList()` có từ Java 16; nó tạo danh sách không thể sửa nhưng **không có yêu cầu loại null giống `List.of` hay `List.copyOf`**. Ngược lại, `Collectors.toUnmodifiableList()` có từ Java 10 và từ chối null. Hai biểu thức **không tương đương về quy tắc null**.

Khi muốn đầu ra vừa unmodifiable vừa null-free, có thể dùng một trong các chiến lược có chủ đích:

~~~java
var cleaned = source.stream().filter(Objects::nonNull).toList();
var result = List.copyOf(cleaned); // Xác nhận không có null
~~~

Hoặc nếu null phải bị từ chối:

~~~java
var result = source.stream()
        .collect(Collectors.toUnmodifiableList()); // NPE khi có null
~~~

Nếu cần thông tin lỗi chi tiết, tốt hơn nên kiểm tra bằng mã validation của nghiệp vụ trước khi gom. Với `Collectors.toUnmodifiableSet` hoặc `Collectors.toUnmodifiableMap`, chính sách từ chối null cũng áp dụng cho phần tử hoặc key/value theo từng API. Với `Collectors.toList()` thông thường, **không nên dựa vào khả năng sửa kết quả** vì API không bảo đảm mutability; muốn điều khiển cụ thể, dùng `toCollection(ArrayList::new)`.

## 9. Tích hợp ở ranh giới API, service và model

### 9.1. Nhận đầu vào có thể thiếu

Giả sử một service nhận danh sách tag từ request. Có hai hợp đồng khác nhau:

**Hợp đồng nghiêm ngặt:** “Danh sách bắt buộc có mặt; từng tag không được null.”

~~~java
static List<String> readTagsStrict(List<String> rawTags) {
    Objects.requireNonNull(rawTags, "rawTags");
    return List.copyOf(rawTags); // Từ chối null element
}
~~~

**Hợp đồng linh hoạt:** “Tag null nghĩa là không có tag ở vị trí đó; bỏ qua mục này.”

~~~java
static List<String> readTagsLenient(List<String> rawTags) {
    Objects.requireNonNull(rawTags, "rawTags");
    var valid = rawTags.stream().filter(Objects::nonNull).toList();
    return List.copyOf(valid);
}
~~~

Cả hai phương thức là mã Java hợp lệ khi đặt trong một lớp và import `List`, `Objects`. Chúng không tương đương về nghiệp vụ. Chọn phương thức dựa vào hợp đồng công khai; không mặc định lọc null mọi nơi.

### 9.2. Tránh hiểu nhầm `var` khiến dữ liệu non-null

~~~java
var input = new ArrayList<String>();
input.add(null); // ArrayList<String> vẫn có thể chứa null
var published = List.copyOf(input); // NPE khi chạy
~~~

Kiểu suy luận của `input` là `ArrayList<String>`; generic `String` không phải chú thích non-null. `var` không chèn kiểm tra null và cũng không biến giá trị nullable thành non-null. Chính factory/copy method mới xác nhận hợp đồng khi được gọi.

### 9.3. Không dùng thông báo NPE làm API kiểm tra lỗi

Thông điệp của ngoại lệ và vị trí stack trace có thể thay đổi giữa JDK/triển khai. Khi nghiệp vụ cần trả lỗi cụ thể cho client, hãy kiểm tra đầu vào rồi chuyển lỗi thành thông báo có cấu trúc trong tầng nhận request; không phân tích chuỗi message của `NullPointerException`.

### 9.4. Chú ý đến nguồn bị thay đổi đồng thời

Nếu collection nguồn bị sửa từ nhiều luồng đúng lúc kiểm tra hoặc tạo snapshot, chuỗi “kiểm tra từng phần tử → `copyOf`” không tự tạo bảo đảm atomic. Cần chiến lược truy cập thread-safe và đồng bộ phù hợp. Việc trả một collection unmodifiable cũng không biến những đối tượng mutable bên trong thành thread-safe.

## 10. Các ngộ nhận cần tránh

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`List<String>` không thể chứa null.” | Tham số generic không phải ràng buộc non-null; `ArrayList<String>` có thể chứa null. |
| “`var` suy luận kiểu nên tự cấm null.” | `var` chỉ xác định kiểu tĩnh, không thay đổi chính sách null. |
| “`List.of` nhận null và giữ lại như `ArrayList`.” | `List.of` ném `NullPointerException`. |
| “`Map.of` chỉ kiểm tra value null.” | Nó từ chối **cả key và value null**. |
| “`List.copyOf` tự lọc phần tử null.” | Nó **từ chối** nguồn có null. |
| “`Collections.unmodifiableList` và `List.copyOf` hoàn toàn giống nhau.” | View phản ánh thay đổi của backing collection, còn `copyOf` tạo kết quả không phản ánh thay đổi nguồn sau đó. |
| “Bất cứ collection không thể sửa nào cũng null-free.” | View có thể chứa null; `Stream.toList()` có thể giữ null. |
| “`Stream.toList` tương đương `Collectors.toUnmodifiableList` ở mọi mặt.” | Cả hai trả kết quả không thể sửa, nhưng khác chính sách null. |
| “Có thể lọc null mà không ảnh hưởng nghiệp vụ.” | Việc bỏ phần tử thay đổi số lượng, vị trí hoặc ý nghĩa dữ liệu. |
| “`Map.copyOf` chỉ cần kiểm tra key.” | Cả key và value của map nguồn đều không được null. |
| “Unmodifiable list bảo đảm phần tử cũng immutable.” | Các object mutable bên trong vẫn có thể thay đổi. |
| “CopyOf luôn tạo đối tượng mới.” | API có thể tái sử dụng collection phù hợp; không dựa vào identity. |

## 11. Bài tập tự kiểm tra

### Bài 1. Chọn cách tạo an toàn

~~~java
var raw = new ArrayList<String>();
raw.add("A");
raw.add(null);
~~~

Hỏi: `List.copyOf(raw)` sẽ có kết quả gì?

**Đáp án:** Ném `NullPointerException` tại thời điểm tạo, không trả về danh sách `[A, null]`.

### Bài 2. Phân biệt view với snapshot

~~~java
var backing = new ArrayList<String>();
backing.add(null);
var view = Collections.unmodifiableList(backing);
backing.add("B");
~~~

Hỏi: `view` chứa gì?

**Đáp án:** View có thể hiển thị `[null, B]`. Nó không thể sửa qua `view.add` nhưng phản ánh thay đổi phía `backing`. Đây không phải một null-free snapshot.

### Bài 3. Đánh giá ba lệnh

~~~java
var a = Stream.<String>of("x", null).toList();
var b = Stream.<String>of("x", null)
        .collect(Collectors.toUnmodifiableList());
var c = Stream.<String>of("x", null)
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());
~~~

**Đáp án:** `a` tạo một danh sách không thể sửa chứa null; `b` ném `NullPointerException`; `c` trả danh sách không thể sửa chứa duy nhất `"x"`. Ba dòng là phương án độc lập vì `b` ném ngoại lệ nếu chạy nối tiếp mà không bắt lỗi.

### Bài 4. Quy tắc map

~~~java
var mutable = new HashMap<String, Integer>();
mutable.put("A", 1);
mutable.put("B", null);
~~~

Hỏi: `Map.copyOf(mutable)` có hợp lệ không?

**Đáp án:** Không; value null khiến `NullPointerException`. Tương tự, map chứa null key cũng bị từ chối.

### Bài 5. Chọn fail-fast hay filter

Hệ thống nhận ba mã định danh `["a", null, "c"]`. `null` ở vị trí thứ hai nghĩa là dữ liệu nhập thiếu thông tin bắt buộc.

**Đáp án:** **Từ chối** với lỗi cụ thể ở vị trí thứ hai, không lọc bỏ rồi chuyển `"c"` sang vị trí mới. Nếu đây là danh sách gợi ý tùy chọn mà null nghĩa là “bỏ gợi ý”, việc lọc có thể hợp lý. Chính sách phải đến từ hợp đồng nghiệp vụ.

### Bài 6. `copyOf` có bảo đảm bất biến sâu?

~~~java
var mutableItem = new StringBuilder("A");
var list = List.of(mutableItem);
mutableItem.append("B");
~~~

**Đáp án:** Không. `list.get(0).toString()` trở thành `"AB"`. Collection không cho thay đổi cấu trúc nhưng phần tử có thể mutable.

### Bài 7. Tại sao `Set.copyOf(List.of(1,1,2))` không tạo ra ba phần tử?

**Đáp án:** `Set` không chứa các phần tử trùng nhau theo quan hệ bằng nhau; `Set.copyOf` cho kết quả có hai giá trị phân biệt. Đây là quy tắc set, độc lập với kiểm tra null.

### Bài 8. Khi nguồn vốn đã unmodifiable

Hỏi: `List.copyOf(existingList)` có luôn trả một đối tượng có `==` khác `existingList` không?

**Đáp án:** Không được giả định. Khi nguồn đã là một unmodifiable list phù hợp, `copyOf` có thể không tạo bản sao mới. Hãy kiểm tra hợp đồng giá trị, không kiểm tra danh tính đối tượng.

## 12. Tài liệu chính thức đang áp dụng

- [Java SE API — `List.of` và `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): danh sách không thể sửa, từ chối null, `copyOf` không phản ánh sửa đổi sau đó của nguồn.
- [Java SE API — `Set.of` và `Set.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): từ chối null, quy tắc phần tử trùng nhau.
- [Java SE API — `Map.of`, `Map.ofEntries` và `Map.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): từ chối null key/value, bản sao không thể sửa.
- [Java SE API — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view chỉ đọc với backing collection, không phải snapshot xác thực null.
- [Java SE API — `Stream.toList()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): danh sách không thể sửa từ Java 16.
- [Java SE API — `Collectors.toUnmodifiableList()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector Java 10 từ chối phần tử null.
- [Java SE API — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra dữ liệu null tại ranh giới.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): nguồn gốc các collection factory từ Java 9, vẫn được dùng hiện nay.

**Quy tắc thực hành:** Ở ranh giới từ dữ liệu chưa tin cậy sang collection xuất bản, **quyết định chính sách null trước**: từ chối đầu vào thiếu bắt buộc, bỏ null chỉ khi hợp đồng cho phép, hoặc mô hình hóa trạng thái thiếu bằng kiểu rõ ràng. Sau đó dùng `List.copyOf`, `Set.copyOf` hoặc `Map.copyOf` để tạo kết quả không thể sửa, null-free và không phản ánh sửa đổi xảy ra sau đó ở nguồn. Không nhầm read-only view hay `Stream.toList()` với một bước kiểm tra null.