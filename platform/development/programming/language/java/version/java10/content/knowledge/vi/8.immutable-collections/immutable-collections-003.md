# List.copyOf, Set.copyOf và Map.copyOf — tạo bản sao collection không sửa được (Java 10+)

Khi ứng dụng xây dựng xong một danh sách, tập hợp hoặc bảng ánh xạ rồi muốn cung cấp dữ liệu để **đọc mà không cho bên nhận thêm, xóa hoặc thay thế phần tử**, Java có ba phương thức tạo bản sao rất hữu ích: `List.copyOf(...)`, `Set.copyOf(...)` và `Map.copyOf(...)`. Cả ba được bổ sung từ **Java 10** và vẫn là API tiêu chuẩn, được dùng trong Java hiện đại.

Các phương thức này tạo **bản sao không sửa được** (*unmodifiable copy*) của nội dung collection/map tại thời điểm gọi. Khi nguồn là collection có thể sửa đổi, việc thêm/xóa/thay ánh xạ trên nguồn sau đó không làm thay đổi cấu trúc nội dung bản sao. Tuy nhiên, đây là **sao chép nông** (*shallow copy*): đối tượng phần tử, khóa và giá trị không được sao chép sâu.

## 1. Ba phương thức và kiểu dữ liệu đầu vào

~~~java
import java.util.List;
import java.util.Set;
import java.util.Map;

// Các lệnh dưới đây là ví dụ đặt trong một phương thức:
var names = List.copyOf(List.of("An", "Bình"));   // List<String>
var codes = Set.copyOf(List.of("A", "B", "A"));    // Set<String>
var prices = Map.copyOf(Map.of("book", 50));       // Map<String, Integer>
~~~

**Chữ ký API**, viết rút gọn:

~~~java
static <E> List<E> copyOf(Collection<? extends E> coll);
static <E> Set<E> copyOf(Collection<? extends E> coll);
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map);
~~~

Ba chữ ký trên chỉ minh họa kiểu và tham số của API; chúng **không phải ba phương thức tự định nghĩa để chép vào lớp**. Cần lưu ý:

- `List.copyOf` nhận **`Collection`**: có thể sao chép `List` hoặc `Set` và các collection tương thích; kết quả là `List`.
- `Set.copyOf` cũng nhận **`Collection`**: có thể nhận `List`, kể cả danh sách chứa giá trị trùng nhau; kết quả là `Set`.
- `Map.copyOf` nhận **`Map`**, không nhận `Collection` hoặc danh sách các cặp tùy ý; kết quả là `Map`.
- Các tham số kiểu generic được bảo toàn theo dữ liệu và ngữ cảnh suy luận kiểu. Khi dùng `var` ở bên trái, ví dụ `var result = List.copyOf(listOfStrings);`, `result` có kiểu tĩnh `List<String>` nếu nguồn có kiểu `Collection<String>`.

**Không phải chỉ vì khai báo có từ `copyOf` mà chắc chắn tạo một đối tượng mới.** API có thể tận dụng lại instance đã có nếu nguồn phù hợp và đã không sửa được. Không dựa vào tham chiếu bằng nhau hay lớp triển khai cụ thể.

## 2. `List.copyOf`: giữ thứ tự duyệt và phần tử trùng

`List.copyOf(Collection<? extends E>)` cho kết quả là một danh sách không sửa được, chứa các phần tử của collection nguồn theo **thứ tự duyệt (iteration order) của nguồn tại thời điểm sao chép**.

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("An", "Bình", "An"));

var snapshot = java.util.List.copyOf(source);

System.out.println(snapshot); // [An, Bình, An]

source.add("Chi");
System.out.println(snapshot); // Vẫn [An, Bình, An]
~~~

*Các lệnh trên là đoạn minh họa trong một phương thức Java.* `List.copyOf` giữ cả hai lần xuất hiện của `"An"` và bảo toàn thứ tự của `ArrayList`. Sau `source.add("Chi")`, `snapshot` vẫn có ba phần tử ban đầu.

Những lời gọi thay đổi danh sách kết quả bị từ chối:

~~~java
// Giả sử snapshot là List do List.copyOf trả về.
// snapshot.add("Dũng");      // Biên dịch được nhưng ném UnsupportedOperationException
// snapshot.remove(0);        // Tương tự
// snapshot.set(0, "Mới");    // Tương tự
~~~

Đây là **lỗi lúc chạy** nếu gọi, không phải lỗi biên dịch: kiểu `List` vẫn khai báo các phương thức `add`, `remove`, `set`; đối tượng cụ thể trả về không hỗ trợ sửa đổi.

Lưu ý khi đầu vào không phải danh sách: `List.copyOf(someSet)` ghi lại **thứ tự iterator của `someSet`** tại lúc gọi. Nếu `someSet` không cam kết thứ tự, kết quả cũng không thể được giả định theo thứ tự chèn hay thứ tự chữ cái. Muốn thứ tự cụ thể, hãy sắp xếp dữ liệu trước khi tạo snapshot.

## 3. `Set.copyOf`: loại phần tử trùng và không đảm bảo thứ tự duyệt

`Set.copyOf(Collection<? extends E>)` tạo tập hợp không sửa được. Vì `Set` chỉ chứa các phần tử khác nhau theo quan hệ bằng nhau, các giá trị trùng của một `List` nguồn được gộp lại:

~~~java
var input = java.util.List.of("A", "B", "A");
var unique = java.util.Set.copyOf(input);

System.out.println(unique.size());    // 2
System.out.println(unique.contains("A")); // true
System.out.println(unique.contains("B")); // true
~~~

`Set.copyOf` **không ném lỗi chỉ vì collection nguồn có phần tử trùng**. Theo tài liệu API, nếu có nhiều đối tượng được coi là trùng nhau, một đối tượng bất kỳ trong số đó có thể được giữ lại; đừng dựa vào tham chiếu nào được chọn.

Điều này khác `Set.of("A", "B", "A")`: phương thức tạo trực tiếp `Set.of` ném **`IllegalArgumentException`** khi các đối số trùng nhau. Đối với `Set.copyOf`, gộp giá trị trùng là hành vi được định nghĩa.

`Set.copyOf` không cam kết thứ tự duyệt. Do đó, **không viết kiểm thử bằng cách so sánh `unique.toString()` với thứ tự cố định** và không cho rằng kết quả giữ thứ tự của một `LinkedHashSet`. Nếu cần thứ tự để hiển thị, có thể chuyển thành danh sách rồi sắp xếp:

~~~java
var sorted = new java.util.ArrayList<>(unique);
sorted.sort(java.util.Comparator.naturalOrder());
System.out.println(sorted); // [A, B]
~~~

Bản thân `sorted` là `ArrayList` có thể sửa đổi. Nếu cần kết quả có thứ tự đã sắp xếp nhưng không sửa được, tạo tiếp `var readOnlySorted = java.util.List.copyOf(sorted);`. Lựa chọn `List` ở đây thể hiện yêu cầu giữ thứ tự, thay vì cố ép `Set.copyOf` cam kết điều nó không bảo đảm.

## 4. `Map.copyOf`: chụp các cặp khóa–giá trị

`Map.copyOf(Map<? extends K, ? extends V>)` tạo map không sửa được với các ánh xạ hiện có tại thời điểm gọi. Thay đổi key/value mapping trong nguồn sau đó không cập nhật kết quả:

~~~java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("A", 1);
source.put("B", 2);

var snapshot = java.util.Map.copyOf(source);

source.put("A", 9);
source.put("C", 3);

System.out.println(snapshot.get("A")); // 1
System.out.println(snapshot.size());    // 2
~~~

Các thao tác sửa `snapshot` như `put`, `remove`, `clear`, `replace` không được hỗ trợ và thường gây `UnsupportedOperationException` nếu gọi. Có thể tra cứu, duyệt `entrySet()`, `keySet()`, `values()` và sử dụng các phương thức đọc của `Map`.

Một `Map` vốn đã không có hai khóa trùng nhau theo hợp đồng `Map`, nên không có bước “gộp duplicate key” từ một `Map` hợp lệ đầu vào. Ngược lại, các phương thức **`Map.of(...)`/`Map.ofEntries(...)`** ném `IllegalArgumentException` nếu cố cung cấp khóa trùng trong lúc tạo.

**`Map.copyOf` không giữ cam kết thứ tự của `LinkedHashMap` hay `TreeMap` đầu vào.** Thứ tự duyệt của map trả về là không được chỉ định. Hãy so sánh bằng `get(key)`, `size()`, `equals(...)` hoặc các cặp khóa/giá trị, thay vì kiểm tra chuỗi `toString()` với thứ tự cố định.

## 5. Bản sao snapshot khác gì unmodifiable view?

Cả `copyOf` và các hàm `Collections.unmodifiableList/Set/Map` đều cung cấp cách đọc thông qua giao diện không cho sửa trực tiếp, nhưng quan hệ với nguồn khác nhau.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Đặt trong một phương thức:
var source = new ArrayList<>(List.of("A", "B"));

var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);

source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

- **`Collections.unmodifiableList(source)`** tạo một *view* không sửa được trên `source`. Ai có tham chiếu đến `source` vẫn có thể sửa nguồn, và `view` phản ánh thay đổi đó.
- **`List.copyOf(source)`** tạo bản sao cấu trúc khi nguồn có thể sửa, nên bản sao không theo các thay đổi thêm/xóa/thay thế phần tử về sau.

Tương tự, `Collections.unmodifiableSet` và `Collections.unmodifiableMap` là các view không sửa trực tiếp được, trong khi `Set.copyOf` và `Map.copyOf` được thiết kế cho bản sao không sửa được.

Cả hai họ API **vẫn hữu ích và hiện còn áp dụng**. Chọn `copyOf` khi cần xuất bản một snapshot tại thời điểm xác định; chọn view khi muốn người đọc quan sát dữ liệu nguồn đang thay đổi nhưng không được sửa dữ liệu thông qua view đó.

## 6. Không sửa được cấu trúc không đồng nghĩa bất biến sâu

`List.copyOf`, `Set.copyOf` và `Map.copyOf` **không clone sâu từng đối tượng**. Với giá trị kiểu tham chiếu có thể sửa đổi, nguồn và bản sao có thể giữ cùng tham chiếu.

~~~java
var item = new StringBuilder("old");

var source = new java.util.ArrayList<>(
        java.util.List.of(item));
var snapshot = java.util.List.copyOf(source);

item.append("!");
System.out.println(snapshot.get(0)); // old!
~~~

`snapshot.add(...)` bị từ chối, nhưng `item.append("!")` thay đổi **đối tượng** mà `snapshot` tham chiếu tới, nên kết quả đọc thay đổi. Điều này không mâu thuẫn với việc snapshot không sửa được: **cấu trúc các phần tử của danh sách không bị thay**, chỉ trạng thái bên trong phần tử thay đổi.

Đối với `Map.copyOf`, các giá trị (*value*) có thể là đối tượng có thể sửa đổi. Một giá trị kiểu `List<String>` có thể vẫn được sửa nếu API cụ thể cho phép. Khóa kiểu mutable thì còn nguy hiểm hơn: nếu sửa trường tham gia `equals/hashCode` sau khi làm khóa của map, các thao tác tra cứu có thể không còn hoạt động đáng tin.

Khi cần dữ liệu *thực sự bất biến sâu* cho giao tiếp giữa các thành phần, hãy thiết kế phần tử/value cũng bất biến (ví dụ `String`, bản ghi có thành phần bất biến) hoặc chủ động sao chép các đối tượng bên trong theo mô hình dữ liệu. Dùng `copyOf` **không tự bảo đảm thread-safety** khi phần tử/giá trị vẫn bị sửa từ nhiều luồng.

## 7. Quy tắc với `null`, duplicate và thứ tự

| Phương thức | Nguồn hợp lệ | Có cho phép `null`? | Trùng lặp | Thứ tự |
| --- | --- | --- | --- | --- |
| `List.copyOf(coll)` | `Collection<? extends E>` | Không; phần tử `null` gây `NullPointerException` | Giữ các phần tử trùng | Giữ thứ tự duyệt của nguồn tại lúc sao chép |
| `Set.copyOf(coll)` | `Collection<? extends E>` | Không; phần tử `null` gây `NullPointerException` | Gộp phần tử bằng nhau, chọn một đại diện bất kỳ | Không cam kết |
| `Map.copyOf(map)` | `Map<? extends K, ? extends V>` | Không; khóa hoặc giá trị `null` gây `NullPointerException` | `Map` nguồn chỉ có một ánh xạ mỗi khóa | Không cam kết |

**Cả ba phương thức đều không nhận nguồn là `null`**: lời gọi với nguồn `null` gây `NullPointerException`.

Ví dụ lỗi cố ý, **không đưa vào chương trình chạy hoàn chỉnh**:

~~~java
// List.copyOf(java.util.Arrays.asList("A", null));
// => NullPointerException vì phần tử null

// Set.copyOf(java.util.Arrays.asList("A", null));
// => NullPointerException vì phần tử null

// var mapWithNull = new java.util.HashMap<String, Integer>();
// mapWithNull.put("A", null);
// Map.copyOf(mapWithNull);
// => NullPointerException vì value null

// java.util.Set.of("A", "A");
// => IllegalArgumentException vì đối số trùng

// java.util.Map.of("A", 1, "A", 2);
// => IllegalArgumentException vì khóa trùng
~~~

**Không nhầm ngoại lệ:** `UnsupportedOperationException` xảy ra khi cố sửa **bản sao đã tạo**; `NullPointerException` xảy ra khi nguồn/giá trị nguồn không hợp lệ với quy tắc `null`; còn `IllegalArgumentException` cho duplicate là quy tắc điển hình của `Set.of` và `Map.of` chứ **không** phải của `Set.copyOf`.

## 8. Chương trình hoàn chỉnh và `stdout` có thể kiểm chứng

Lưu mã sau vào tệp **`CopyOfDemo.java`** (chương trình tương thích Java 10+, dùng tốt trên JDK 17+):

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CopyOfDemo {
    public static void main(String[] args) {
        var sourceList = new ArrayList<>(List.of("A", "B", "A"));
        var list = List.copyOf(sourceList);

        sourceList.add("C");
        System.out.println("list=" + list);
        System.out.println("sourceList=" + sourceList);

        // Set.copyOf nhận phần tử trùng, kết quả chỉ giữ 2 giá trị.
        var set = Set.copyOf(List.of("A", "B", "A"));
        System.out.println("setSize=" + set.size());
        System.out.println("setHasA=" + set.contains("A"));
        System.out.println("setHasB=" + set.contains("B"));

        var sourceMap = new LinkedHashMap<String, Integer>();
        sourceMap.put("A", 1);
        sourceMap.put("B", 2);
        var map = Map.copyOf(sourceMap);

        sourceMap.put("A", 9);
        sourceMap.put("C", 3);
        System.out.println("mapA=" + map.get("A"));
        System.out.println("mapSize=" + map.size());

        try {
            list.add("Z");
        } catch (UnsupportedOperationException ex) {
            System.out.println("listAdd=blocked");
        }

        try {
            set.remove("A");
        } catch (UnsupportedOperationException ex) {
            System.out.println("setRemove=blocked");
        }

        try {
            map.put("D", 4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("mapPut=blocked");
        }

        var item = new StringBuilder("old");
        var objects = new ArrayList<>(List.of(item));
        var shallow = List.copyOf(objects);

        item.append("!");
        System.out.println("shallow=" + shallow.get(0));
    }
}
~~~

Biên dịch và chạy bằng terminal ở thư mục chứa tệp:

~~~bash
javac CopyOfDemo.java
java CopyOfDemo
~~~

Kết quả chuẩn:

~~~text
list=[A, B, A]
sourceList=[A, B, A, C]
setSize=2
setHasA=true
setHasB=true
mapA=1
mapSize=2
listAdd=blocked
setRemove=blocked
mapPut=blocked
shallow=old!
~~~

Vì sao `stdout` không in trực tiếp toàn bộ `Set` hoặc `Map`? Thứ tự duyệt của chúng **không được cam kết**, nên chương trình kiểm tra `size()`, `contains(...)` và `get(...)` để kết quả ổn định trên các lần chạy.

Giải thích lần lượt:

1. `List.copyOf` giữ bản sao ba phần tử tại lúc gọi; thêm `"C"` vào nguồn không thay đổi snapshot.
2. `Set.copyOf` gộp hai lần xuất hiện của `"A"` nên kích thước bằng 2.
3. `Map.copyOf` giữ giá trị `"A" -> 1` và chỉ hai khóa ban đầu, dù nguồn đã đổi `"A" -> 9` và thêm `"C"`.
4. Ba thao tác sửa bản sao gây `UnsupportedOperationException` và được bắt tại từng khối `catch`.
5. `StringBuilder` được chia sẻ giữa nguồn và snapshot, nên sửa nội dung phần tử vẫn được nhìn thấy từ `List.copyOf`.

## 9. Khi nào sử dụng trong ứng dụng?

### Phòng vệ khi nhận hoặc trả về collection

Một lớp có thể nhận danh sách từ bên ngoài và giữ snapshot để người gọi không sửa trực tiếp cấu trúc dữ liệu nội bộ thông qua danh sách cũ:

~~~java
import java.util.List;

public final class CourseCatalog {
    private final List<String> courses;

    public CourseCatalog(List<String> courses) {
        this.courses = List.copyOf(courses);
    }

    public List<String> courses() {
        return courses;
    }
}
~~~

Đây là **một lớp hoàn chỉnh nhưng không có `main`**; muốn dùng cần tạo `new CourseCatalog(...)` trong chương trình. `List.copyOf(courses)` cũng từ chối đầu vào `null` hoặc có phần tử `null`, giúp lớp giữ một hợp đồng dữ liệu rõ ràng.

Với danh sách `String` (kiểu bất biến), snapshot trên đáp ứng khá tốt yêu cầu không cho thay đổi cấu trúc và nội dung phần tử. Với danh sách các đối tượng có thể sửa, vẫn cần cân nhắc sao chép sâu nếu đó là hợp đồng của lớp.

Tương tự:

~~~java
// Ví dụ trong phương thức hoặc constructor:
var allowedRoles = Set.copyOf(rolesFromConfig);
var limits = Map.copyOf(limitsFromConfig);
~~~

Giả sử `rolesFromConfig` là `Collection<String>` và `limitsFromConfig` là `Map<String, Integer>`, hai kết quả không theo các phép sửa cấu trúc của nguồn sau khi snapshot được tạo.

### Xây dựng dữ liệu xong mới chốt

~~~java
var buffer = new java.util.ArrayList<String>();
buffer.add("Module A");
buffer.add("Module B");

var published = java.util.List.copyOf(buffer);
// Không được published.add("Module C");
~~~

Đây là cách phổ biến khi xử lý dữ liệu: giai đoạn xây dựng dùng collection có thể sửa; đến thời điểm công bố thì tạo collection không sửa được. Nếu cần bổ sung dữ liệu sau này, tạo một collection mutable mới, thay đổi nó rồi tạo snapshot mới; không sửa trực tiếp snapshot cũ.

### Khi nào không cần copyOf?

Khi các giá trị đã biết trực tiếp ngay trong mã, có thể tạo collection không sửa được bằng:

~~~java
var roles = java.util.Set.of("USER", "ADMIN");
var days = java.util.List.of("Mon", "Tue");
var prices = java.util.Map.of("A", 10, "B", 20);
~~~

`List.of`, `Set.of` và `Map.of` được bổ sung từ Java 9 và vẫn được sử dụng. Chúng nhận các giá trị trực tiếp; `copyOf` đặc biệt phù hợp khi **đã có một collection/map nguồn** và muốn snapshot cấu trúc của nó.

Đừng gọi `copyOf` lặp lại ở mỗi lượt truy cập hay mỗi lần duyệt nếu không cần thiết. Đối với nguồn mutable, việc tạo bản sao mới thường có chi phí tương ứng với số phần tử hoặc ánh xạ cần sao chép. Chọn thời điểm snapshot rõ ràng.

## 10. Một số giới hạn cần nhớ trong thực tế

**Không bảo đảm tạo object mới mỗi lần.** Khi nguồn đã là một tập hợp/map không sửa được phù hợp, triển khai có thể dùng lại instance. Đây là tối ưu được API cho phép; đừng kiểm tra `original == copy` để suy đoán snapshot đã “đúng” hoặc chưa. Đối với các collection không sửa được do factory cung cấp, các đối tượng được xem là *value-based*: ưu tiên `equals` và tránh phụ thuộc identity hay khóa đồng bộ vào instance.

**Không bảo đảm thứ tự cho `Set.copyOf`/`Map.copyOf`.** Nếu nghiệp vụ cần duyệt theo thứ tự cố định, cần thiết kế rõ ràng dữ liệu có thứ tự, ví dụ danh sách các cặp khóa–giá trị hoặc một cấu trúc sắp xếp phù hợp. Đừng dựa vào kết quả chạy trên một JDK cụ thể.

**Không chứa `null`.** Nếu dữ liệu nguồn có thể chứa `null`, hãy xác định quy tắc nghiệp vụ: loại phần tử, thay thế bằng giá trị hợp lệ hoặc từ chối dữ liệu bằng thông báo thích hợp trước khi sao chép. Không dùng `copyOf` để âm thầm bỏ qua `null` vì API sẽ ném ngoại lệ.

**Không biến collection lồng nhau thành bất biến sâu.** Nếu nguồn là `List<List<String>>`, `List.copyOf(source)` chỉ khóa cấu trúc danh sách ngoài; danh sách con có thể vẫn sửa được. Có thể tạo snapshot từng cấp khi đó là yêu cầu dữ liệu:

~~~java
var mutableRows = new java.util.ArrayList<java.util.List<String>>();
mutableRows.add(new java.util.ArrayList<>(java.util.List.of("A")));

var nested = mutableRows.stream()
        .map(java.util.List::copyOf)
        .toList(); // Java 16+: List không sửa được ở cấp ngoài

// Các danh sách con cũng là List không sửa được do List.copyOf.
~~~

Ví dụ lồng nhau yêu cầu Java 16+ do dùng `Stream.toList()`; các ví dụ chính của bài không cần API này. Cách sao chép theo cấp vẫn chỉ bảo vệ được đến mức độ phần tử ở trong cùng cũng bất biến; nếu phần tử là đối tượng mutable, phải xử lý riêng.

**Không coi “chỉ đọc” là tự động an toàn đa luồng.** Cấu trúc bản sao không thể sửa qua API của nó, nhưng các phần tử mutable vẫn có thể bị chỉnh sửa từ nơi khác. Cần thiết kế đối tượng bên trong và cách công bố dữ liệu phù hợp khi có nhiều luồng.

## 11. Tự kiểm tra

Xét các đoạn độc lập (giả định có `import java.util.*;`):

~~~java
// A: Chụp snapshot
var src = new ArrayList<>(List.of(1, 2));
var snap = List.copyOf(src);
src.set(0, 99);

// B: Tạo Set từ dữ liệu trùng
var unique = Set.copyOf(List.of("X", "X", "Y"));

// C: Map có dữ liệu null
var m = new HashMap<String, Integer>();
m.put("X", null);
// var bad = Map.copyOf(m);

// D: Phần tử mutable
var item = new StringBuilder("A");
var items = List.copyOf(List.of(item));
item.append("B");
~~~

**Câu hỏi:**

1. `snap.get(0)` sau A bằng bao nhiêu?
2. `unique.size()` sau B bằng bao nhiêu? Có bảo đảm thứ tự in không?
3. Nếu bỏ chú thích ở `Map.copyOf(m)` trong C thì xảy ra điều gì?
4. `items.get(0).toString()` sau D bằng gì? `items.add(...)` có được không?

**Đáp án:**

1. `1`; snapshot không chịu ảnh hưởng của phép thay phần tử trong nguồn.
2. `2`; `"X"` trùng được gộp, và thứ tự duyệt của `Set` kết quả không cam kết.
3. Ném `NullPointerException` vì map nguồn chứa giá trị `null`.
4. `"AB"` do tham chiếu đến cùng `StringBuilder`; gọi `items.add(...)` sẽ bị từ chối bởi `UnsupportedOperationException`.

## 12. Tổng kết và tài liệu tham khảo

- **`List.copyOf`**: từ `Collection` sang `List` không sửa được; **giữ thứ tự duyệt và phần tử trùng**.
- **`Set.copyOf`**: từ `Collection` sang `Set` không sửa được; **gộp giá trị trùng, không cam kết thứ tự**.
- **`Map.copyOf`**: từ `Map` sang `Map` không sửa được; **chụp các ánh xạ tại lúc gọi, không cam kết thứ tự**.
- **Cả ba không nhận nguồn `null` và nội dung `null`**; chúng tạo snapshot cấu trúc từ nguồn mutable nhưng chỉ sao chép nông các phần tử/khóa/giá trị.
- **`copyOf` khác `Collections.unmodifiable...`**: snapshot không theo các sửa đổi cấu trúc nguồn, còn unmodifiable view phản ánh nguồn được bọc.
- **Đừng phụ thuộc identity**: kết quả có thể tái sử dụng instance đã có nếu thích hợp.

Tham khảo chính thức:

- [Java SE 26 — List.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 26 — Set.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection))
- [Java SE 26 — Map.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)
