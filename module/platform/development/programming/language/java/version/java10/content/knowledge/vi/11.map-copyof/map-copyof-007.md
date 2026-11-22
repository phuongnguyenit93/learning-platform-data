# Giới hạn `put`, `remove`, `replace` và các thao tác cập nhật trên `Map.copyOf` (Java 10+)

## 1. Hiểu đúng hợp đồng: `Map.copyOf` tạo map không sửa được

`Map.copyOf(source)` được giới thiệu từ **Java 10** và vẫn là API tiêu chuẩn trong Java hiện đại. Nó nhận một `Map` nguồn, trả về một **unmodifiable Map** chứa các ánh xạ khóa–giá trị của nguồn tại thời điểm sao chép. Sau đó, các thay đổi cấu trúc hay thay giá trị ánh xạ trên **map nguồn** không làm bản sao tự cập nhật.

~~~java
import java.util.HashMap;
import java.util.Map;

// Đoạn minh họa đặt trong một phương thức:
var source = new HashMap<String, Integer>();
source.put("A", 1);
source.put("B", 2);

var readOnly = Map.copyOf(source); // Map<String, Integer>

System.out.println(readOnly.get("A")); // 1
~~~

**Quy tắc trọng tâm:** `readOnly` có thể được **đọc** bằng `get`, `containsKey`, `containsValue`, `size`, `isEmpty`, `forEach`..., nhưng **không thể thay đổi tập ánh xạ** của nó bằng `put`, `remove`, `replace`, `clear`, `merge`, `compute...` hay các phương thức cập nhật khác.

Nếu cố thực hiện một thao tác cập nhật trên đối tượng do `Map.copyOf` trả về, API ném **`UnsupportedOperationException`**. Điều này xảy ra ở **thời điểm chạy**, không phải lỗi biên dịch: biến có kiểu giao diện `Map<K,V>`, mà giao diện vẫn khai báo các phương thức cập nhật.

Đừng nhầm **không sửa được cấu trúc map** với **bất biến sâu** (*deep immutability*). Nếu giá trị hoặc khóa là đối tượng mutable, trạng thái bên trong những đối tượng ấy vẫn có thể đổi; phần 7 sẽ làm rõ.

## 2. Chữ ký và kiểu dữ liệu

Chữ ký rút gọn của API:

~~~java
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map)
~~~

Đây là **chữ ký minh họa của thư viện**, không phải phương thức cần tự cài đặt. Khi dùng `Map.copyOf`, Java giữ kiểu generic phù hợp của khóa và giá trị.

~~~java
Map<String, Integer> source = Map.of("A", 1, "B", 2);
var snapshot = Map.copyOf(source); // Map<String, Integer>
~~~

Giá trị `snapshot` không phải là một `HashMap` mutable chỉ vì `source` có thể là `HashMap`. Kiểu tĩnh được suy luận là `Map<String, Integer>`, và **bản thân đối tượng trả về không hỗ trợ cập nhật**, bất kể bạn khai báo bằng `var` hay kiểu `Map<String,Integer>` tường minh.

`Map.copyOf` từ chối **nguồn `null`, khóa `null` hoặc giá trị `null`** bằng `NullPointerException`. Để các ví dụ bên dưới tập trung vào giới hạn mutator, nguồn luôn có khóa và giá trị khác `null`.

## 3. `put` và `putAll`: không được thêm hoặc ghi đè

### `put` không được thêm khóa mới

~~~java
var prices = Map.copyOf(Map.of("book", 100));

// prices.put("pen", 20);
// Ném UnsupportedOperationException nếu chạy.
~~~

Không thể gán thêm `"pen" -> 20` vào map này. Hành vi khác `HashMap`, nơi `put` có thể thêm khóa mới.

### `put` cũng không được ghi đè giá trị của khóa cũ

~~~java
var prices = Map.copyOf(Map.of("book", 100));

// prices.put("book", 150);
// Vẫn ném UnsupportedOperationException.
~~~

Việc khóa `"book"` đã tồn tại **không tạo ngoại lệ cho phép cập nhật**. `put` vừa là phương thức thêm, vừa là phương thức thay giá trị; cả hai ý định đều trái hợp đồng của `Map.copyOf`.

### `putAll` cũng bị chặn

~~~java
var prices = Map.copyOf(Map.of("book", 100));

// prices.putAll(Map.of("pen", 20));
// Ném UnsupportedOperationException.
~~~

`putAll` chỉ là một cách bổ sung/ghi đè nhiều ánh xạ; không phải đường vòng để sửa map không sửa được.

## 4. `remove`, `clear`: không được xóa ánh xạ

`Map` cung cấp cả biến thể xóa theo khóa và xóa có điều kiện:

~~~java
var statuses = Map.copyOf(Map.of("A", 1, "B", 2));

// statuses.remove("A");     // UnsupportedOperationException
// statuses.remove("A", 1);  // UnsupportedOperationException
// statuses.clear();         // UnsupportedOperationException
~~~

- `remove(key)` yêu cầu bỏ ánh xạ theo khóa.
- `remove(key, value)` yêu cầu bỏ ánh xạ **chỉ nếu** giá trị hiện tại khớp.
- `clear()` yêu cầu xóa tất cả ánh xạ.

Đây đều là thao tác thay đổi nội dung map và không được hỗ trợ. Không dùng `remove(key, value)` để lách giới hạn chỉ vì nó có điều kiện.

**Với các map khác triển khai giao diện `Map`**, đặc tả có một sắc thái: một số thao tác phá hủy (*destructive operations*) có thể không ném `UnsupportedOperationException` nếu lần gọi **không gây thay đổi gì**. Vì vậy, **đừng viết logic nghiệp vụ dựa vào việc một lời gọi no-op có ném ngoại lệ hay không**; trường hợp cần xử lý ở đây là map do `Map.copyOf` trả về, mà hợp đồng của nhóm factory map không sửa được là không cho các mutator cập nhật.

Để xác định có khóa, dùng `containsKey` hoặc `get` theo ngữ nghĩa ứng dụng, thay vì gọi `remove` như một phép kiểm tra.

## 5. `replace` và `replaceAll`: không được thay giá trị

`Map` có ba cách thường gặp để thay giá trị:

~~~java
var counts = Map.copyOf(Map.of("A", 1, "B", 2));

// counts.replace("A", 10);
// counts.replace("A", 1, 10);
// counts.replaceAll((key, value) -> value + 1);
~~~

Các lời gọi đều là mutator và bị từ chối bằng `UnsupportedOperationException` khi thực thi trên map không sửa được.

| Phương thức | Mục đích với map mutable | Trên map `copyOf` |
| --- | --- | --- |
| `replace(key, newValue)` | Thay giá trị nếu khóa tồn tại | Không hỗ trợ |
| `replace(key, oldValue, newValue)` | Thay khi giá trị hiện tại khớp `oldValue` | Không hỗ trợ |
| `replaceAll((k, v) -> ...)` | Tính và đặt lại giá trị cho các ánh xạ | Không hỗ trợ |

Không phải vì `replaceAll` nhận lambda mà nó trở thành thao tác đọc: hàm được dùng để **tạo giá trị mới gán vào map**, nên nó mang ý nghĩa cập nhật.

Nếu cần tính giá trị mới để hiển thị nhưng **không sửa map**, hãy duyệt bằng `forEach` hoặc tạo một map kết quả mới:

~~~java
var original = Map.copyOf(Map.of("A", 1, "B", 2));

original.forEach((key, value) ->
        System.out.println(key + ":" + (value + 1)));

// Tạo một bản mutable mới nếu cần lưu giá trị đã biến đổi:
var adjusted = new java.util.HashMap<>(original);
adjusted.replaceAll((key, value) -> value + 1);

var published = Map.copyOf(adjusted);
~~~

Lưu ý: `forEach` ở trên có thứ tự in **không được bảo đảm** vì `Map.copyOf` không cam kết thứ tự duyệt. Đoạn này chỉ minh họa API, không dùng làm `stdout` cố định trong bài.

## 6. Các mutator khác: `putIfAbsent`, `compute*`, `merge`

Ngoài `put`/`remove`/`replace`, Java hiện đại còn các phương thức cập nhật theo điều kiện hoặc tính toán lại ánh xạ.

~~~java
var stock = Map.copyOf(Map.of("A", 1, "B", 2));

// stock.putIfAbsent("C", 3);                // Không hỗ trợ
// stock.computeIfAbsent("C", key -> 3);    // Không hỗ trợ
// stock.computeIfPresent("A", (k, v) -> v + 1); // Không hỗ trợ
// stock.compute("A", (k, v) -> v + 1);     // Không hỗ trợ
// stock.merge("A", 5, Integer::sum);       // Không hỗ trợ
~~~

Ý nghĩa của các API khi dùng trên map mutable:

- **`putIfAbsent`:** thêm khi chưa có ánh xạ thích hợp.
- **`computeIfAbsent`:** tạo và đặt giá trị khi chưa có giá trị hiện hữu phù hợp.
- **`computeIfPresent`:** tính lại và cập nhật giá trị khi khóa đang ánh xạ đến giá trị phù hợp.
- **`compute`:** tính lại ánh xạ, có thể thêm, thay hoặc xóa tùy giá trị trả về.
- **`merge`:** gộp một giá trị mới với giá trị hiện có; có thể thay hoặc xóa ánh xạ.

Tất cả là **phương thức cập nhật**, dù trông giống phép tính. Không dùng `computeIfAbsent` trên một bản `Map.copyOf` với kỳ vọng nó sẽ trở thành bộ nhớ đệm có thể bổ sung dữ liệu. Để làm cache mutable, cần thiết kế dữ liệu khác, ví dụ một `HashMap`/`ConcurrentHashMap` tùy yêu cầu đồng thời, chứ không phải gỡ bỏ tính không sửa được của bản sao.

**Không suy luận rằng lambda luôn được thực thi trước khi lỗi xảy ra.** Trên một số cài đặt, thao tác có thể bị từ chối ngay tại lúc gọi, trước cả khi callback được chạy. Vì vậy không đặt side effect quan trọng vào hàm tính toán rồi mong nó chạy dù map không sửa được.

## 7. Không thể sửa gián tiếp qua `entrySet`, `keySet`, `values`

Các phương thức truy cập theo view vẫn dùng được để **đọc**:

~~~java
var catalog = Map.copyOf(Map.of("A", 1, "B", 2));

System.out.println(catalog.keySet().contains("A")); // true
System.out.println(catalog.values().contains(2));   // true
System.out.println(catalog.entrySet().size());      // 2
~~~

Nhưng không thể tìm đường vòng cập nhật qua các view:

~~~java
var catalog = Map.copyOf(Map.of("A", 1, "B", 2));

// catalog.keySet().remove("A"); // Không được xóa qua keySet
// catalog.values().remove(1);   // Không được xóa qua values
// catalog.entrySet().remove(Map.entry("A", 1)); // Không được xóa entry
~~~

Một `Map.Entry<K,V>` đại diện cho cặp khóa–giá trị. Với map có thể sửa, một số entry có thể cho phép `setValue`. Với entry do `entrySet` của `Map.copyOf` cung cấp, hành vi sửa cũng bị từ chối:

~~~java
var catalog = Map.copyOf(Map.of("A", 1, "B", 2));

var firstEntry = catalog.entrySet().iterator().next();

// firstEntry.setValue(99); // UnsupportedOperationException.
~~~

Không dùng `Iterator.remove()` trên view của map không sửa được để loại một phần tử. Tập `keySet`, tập `entrySet` và collection `values` không cho thay đổi map mà chúng biểu diễn.

**Phân biệt rõ:** `entry.getValue()` **trả về giá trị để đọc** và vẫn được hỗ trợ; `entry.setValue(...)` **thay giá trị ánh xạ** và bị từ chối. Với value là một đối tượng mutable, gọi phương thức sửa **trạng thái bên trong đối tượng** lại là chuyện khác — phần 9.

## 8. Chương trình đầy đủ: thử từng thao tác và quan sát `UnsupportedOperationException`

Lưu tệp **`MapCopyOfMutatorsDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class MapCopyOfMutatorsDemo {

    private static void attempt(String name, Runnable operation) {
        try {
            operation.run();
            System.out.println(name + "=unexpected");
        } catch (UnsupportedOperationException ex) {
            System.out.println(name + "=blocked");
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashMap<String, Integer>();
        source.put("A", 1);
        source.put("B", 2);

        var snapshot = Map.copyOf(source);

        System.out.println("initialSize=" + snapshot.size());
        System.out.println("initialA=" + snapshot.get("A"));

        // Các thao tác này sửa SOURCE, không sửa SNAPSHOT.
        source.put("A", 10);
        source.remove("B");
        source.put("C", 3);

        System.out.println("sourceA=" + source.get("A"));
        System.out.println("sourceHasB=" + source.containsKey("B"));
        System.out.println("snapshotA=" + snapshot.get("A"));
        System.out.println("snapshotHasB=" + snapshot.containsKey("B"));
        System.out.println("snapshotHasC=" + snapshot.containsKey("C"));

        // Thử các mutator trên snapshot.
        attempt("put", () -> snapshot.put("C", 3));
        attempt("putIfAbsent", () -> snapshot.putIfAbsent("C", 3));
        attempt("putAll", () -> snapshot.putAll(Map.of("C", 3)));
        attempt("remove", () -> snapshot.remove("A"));
        attempt("remove2", () -> snapshot.remove("A", 1));
        attempt("replace", () -> snapshot.replace("A", 7));
        attempt("replace3", () -> snapshot.replace("A", 1, 7));
        attempt("replaceAll",
                () -> snapshot.replaceAll((key, value) -> value + 1));
        attempt("computeIfAbsent",
                () -> snapshot.computeIfAbsent("C", key -> 3));
        attempt("computeIfPresent",
                () -> snapshot.computeIfPresent(
                        "A", (key, value) -> value + 1));
        attempt("compute",
                () -> snapshot.compute(
                        "A", (key, value) -> value + 1));
        attempt("merge",
                () -> snapshot.merge("A", 5, Integer::sum));
        attempt("clear", () -> snapshot.clear());

        // Sửa qua view và Map.Entry cũng bị chặn.
        attempt("entrySet.setValue",
                () -> snapshot.entrySet().iterator().next().setValue(6));
        attempt("keySet.remove",
                () -> snapshot.keySet().remove("A"));
        attempt("values.remove",
                () -> snapshot.values().remove(1));
        attempt("entrySet.remove",
                () -> snapshot.entrySet().remove(Map.entry("A", 1)));

        System.out.println("finalSize=" + snapshot.size());
        System.out.println("finalA=" + snapshot.get("A"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**; các tính năng sử dụng trong ví dụ tương thích **Java 10 trở lên**:

~~~bash
javac MapCopyOfMutatorsDemo.java
java MapCopyOfMutatorsDemo
~~~

`stdout` được kiểm chứng:

~~~text
initialSize=2
initialA=1
sourceA=10
sourceHasB=false
snapshotA=1
snapshotHasB=true
snapshotHasC=false
put=blocked
putIfAbsent=blocked
putAll=blocked
remove=blocked
remove2=blocked
replace=blocked
replace3=blocked
replaceAll=blocked
computeIfAbsent=blocked
computeIfPresent=blocked
compute=blocked
merge=blocked
clear=blocked
entrySet.setValue=blocked
keySet.remove=blocked
values.remove=blocked
entrySet.remove=blocked
finalSize=2
finalA=1
~~~

Mỗi dòng `...=blocked` cho biết phương thức đã ném `UnsupportedOperationException` và được hàm `attempt` bắt lại. Không có dòng `...=unexpected` vì không có thao tác cập nhật nào được thực hiện thành công trong ví dụ.

Dữ liệu vẫn giữ nguyên tại thời điểm snapshot: `"A"` có giá trị `1`, `"B"` vẫn còn và `"C"` không có mặt. Chương trình **không in toàn bộ map** nên không phụ thuộc thứ tự duyệt không được bảo đảm của `Map.copyOf`.

## 9. Thay đổi map nguồn và thay đổi trạng thái của value: hai vấn đề khác nhau

### Sửa map nguồn sau khi sao chép không đổi ánh xạ trong snapshot

~~~java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 1);

var snapshot = Map.copyOf(source); // A -> 1

source.put("A", 9);
source.put("B", 2);
source.remove("A");

System.out.println(snapshot.get("A"));          // 1
System.out.println(snapshot.containsKey("B"));  // false
~~~

`Map.copyOf` lưu **bản sao cấu trúc ánh xạ**. Các thao tác trên `source` có thể hợp lệ nếu nguồn mutable, nhưng không làm `snapshot` tự thay đổi. Để chụp trạng thái nguồn sau cập nhật, cần **gọi `Map.copyOf(source)` một lần nữa**.

### Bản sao không sửa được nhưng vẫn là sao chép nông

~~~java
var box = new StringBuilder("old");
var source = new java.util.HashMap<String, StringBuilder>();
source.put("A", box);

var snapshot = Map.copyOf(source);

box.append("!");
System.out.println(snapshot.get("A")); // old!

source.put("A", new StringBuilder("new"));
System.out.println(snapshot.get("A")); // Vẫn old!
~~~

Ở dòng `box.append("!")`, cả source và snapshot đang tham chiếu đến **cùng một đối tượng `StringBuilder`**, nên trạng thái có thể được quan sát thông qua `snapshot` thay đổi. Đó **không** phải `Map.put` hoặc `Map.replace`, cũng không làm bộ cặp khóa–giá trị của snapshot đổi tham chiếu.

Sau `source.put("A", new StringBuilder("new"))`, nguồn giữ **tham chiếu mới**, nhưng snapshot vẫn giữ **tham chiếu cũ** với nội dung `old!`.

**Với khóa mutable:** tuyệt đối tránh thay đổi trạng thái của khóa ảnh hưởng đến `equals` hoặc `hashCode` sau khi dùng làm khóa của map. Việc này có thể làm tra cứu sai hoặc vi phạm giả định của ứng dụng; `Map.copyOf` không tự khóa trạng thái của khóa.

### Nếu cần bất biến sâu

Với giá trị là `List<String>` mutable, có thể tạo bản sao không sửa được ở **mỗi cấp dữ liệu**:

~~~java
var source = new java.util.HashMap<String, java.util.List<String>>();
source.put("group", new java.util.ArrayList<>(
        java.util.List.of("A", "B")));

var frozenValues = new java.util.HashMap<String, java.util.List<String>>();

source.forEach((key, value) ->
        frozenValues.put(key, java.util.List.copyOf(value)));

var published = java.util.Map.copyOf(frozenValues);
~~~

`published` không cho sửa các ánh xạ; mỗi `List` value cũng không cho sửa cấu trúc. Trong ví dụ, `String` bất biến nên hai cấp này đáp ứng nhu cầu phổ biến. Với các đối tượng con vẫn mutable, phải đánh giá nhu cầu sao chép sâu tiếp.

## 10. Cần cập nhật dữ liệu? Dùng bản mutable trung gian rồi tạo snapshot mới

Mẫu thiết kế phổ biến: **xây dựng/cập nhật trên map mutable**, sau đó công bố một bản đọc độc lập.

~~~java
import java.util.HashMap;
import java.util.Map;

// Giả sử published là Map<String, Integer> đã tạo bằng Map.copyOf:
var editable = new HashMap<>(published);

editable.put("C", 3);
editable.remove("B");
editable.replace("A", 10);

var nextSnapshot = Map.copyOf(editable);
~~~

`published` vẫn là bản snapshot trước đó; `nextSnapshot` thể hiện các ánh xạ sau khi thay đổi. Điều này hữu ích khi muốn **đóng gói trạng thái mới** mà không để người đọc nắm tham chiếu có thể sửa tới bản dữ liệu đã công bố.

Điểm cần nhớ: `new HashMap<>(published)` tạo **bản sao mutable của cấu trúc ánh xạ**; nó cũng là **sao chép nông**, không clone sâu từng khóa/giá trị.

Nếu nhu cầu của ứng dụng là cập nhật liên tục trong cùng một map, **đừng dùng `Map.copyOf` làm kho lưu trữ mutable**. Hãy giữ một `HashMap` hoặc map tương thích cho phần chịu trách nhiệm cập nhật; dùng `Map.copyOf` ở biên nơi cần bản đọc không cho sửa.

## 11. Phân biệt với unmodifiable view

`Collections.unmodifiableMap(source)` cũng chặn sửa trực tiếp **qua view**, nhưng **phản ánh thay đổi của nguồn** vì nó bọc cùng map nguồn.

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

// Đặt trong một phương thức:
var source = new HashMap<String, Integer>();
source.put("A", 1);

var view = Collections.unmodifiableMap(source);
var snapshot = Map.copyOf(source);

source.put("A", 7);
source.put("B", 2);

System.out.println(view.get("A"));               // 7
System.out.println(snapshot.get("A"));           // 1
System.out.println(view.containsKey("B"));        // true
System.out.println(snapshot.containsKey("B"));    // false
~~~

Cả `view.put(...)` và `snapshot.put(...)` đều không được hỗ trợ, nhưng cách dữ liệu **được quan sát sau khi nguồn thay đổi** là khác nhau.

**Chọn `Map.copyOf`** khi muốn snapshot dữ liệu tại một thời điểm. **Chọn `Collections.unmodifiableMap`** khi cố ý muốn bên nhận thấy trạng thái luôn đổi của nguồn mà không được sửa thông qua chính view đó.

## 12. Lưu ý: `null`, thứ tự, identity và chạy đồng thời

- **`null`:** `Map.copyOf` không cho nguồn `null`, khóa `null` hoặc giá trị `null`. Trường hợp đó ném `NullPointerException` ngay trong quá trình tạo bản sao. Đừng dùng `Map.copyOf` để tự loại null; cần chuẩn hóa hoặc từ chối đầu vào có chủ đích.
- **Thứ tự:** map trả về không cam kết thứ tự duyệt. Ngay cả nếu nguồn là `LinkedHashMap` hoặc `TreeMap`, không kiểm tra thứ tự `entrySet()` hay `toString()` của snapshot như một hợp đồng.
- **Tham chiếu:** `Map.copyOf` có thể dùng lại một đối tượng map đã không sửa được và phù hợp; không đảm bảo luôn tạo instance mới. Không dựa vào `==` để suy luận ý nghĩa “copy”.
- **Đồng thời:** `Map.copyOf` không tự cung cấp snapshot nguyên tử nếu có luồng khác sửa nguồn trong lúc đang sao chép. Khi yêu cầu nhất quán, hãy đồng bộ quy trình đọc/sao chép hoặc dùng kiến trúc dữ liệu có bảo đảm phù hợp.
- **Đối tượng mutable:** không thể xem map đã sao chép là bất biến sâu hoặc tự động an toàn đa luồng chỉ vì không gọi được `put`; khóa/giá trị bên trong vẫn có thể bị sửa từ nơi khác.

## 13. Sai lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| “`Map.copyOf` trả về map mới để tiếp tục `put`.” | Nó trả về map **không sửa được**; muốn sửa dùng bản mutable trung gian. |
| “`replace` có điều kiện thì được phép.” | Các mutator đều không được hỗ trợ trên map kết quả. |
| “`computeIfAbsent` chỉ đọc nếu khóa có sẵn.” | Đây vẫn là một **phương thức cập nhật**, không phải API đọc chuyên dụng. |
| “Không thể `put` nhưng có thể `entry.setValue`.” | `entrySet()` cũng không cho đổi ánh xạ. |
| “`keySet().remove`/`values().remove` là đường vòng hợp lệ.” | Không thể xóa ánh xạ qua các view của map không sửa được. |
| “Sửa `source.put` sẽ cập nhật bản copy.” | Không; snapshot không phản ánh thay đổi ánh xạ nguồn về sau. |
| “Giá trị `StringBuilder` trong map không thể đổi nội dung.” | Có thể đổi trạng thái phần tử mutable; bản sao chỉ sao chép nông. |
| “Không sửa được nghĩa là Java cấm gọi mutator ngay lúc biên dịch.” | Phương thức tồn tại trên giao diện `Map`; đối tượng ném `UnsupportedOperationException` lúc chạy. |

## 14. Bài tập tự kiểm tra

Cho map sau:

~~~java
var source = new java.util.HashMap<String, Integer>();
source.put("X", 10);
source.put("Y", 20);

var copy = java.util.Map.copyOf(source);
~~~

**Câu A.** Sau khi chạy `source.put("X", 99); source.remove("Y");`, hai biểu thức `copy.get("X")` và `copy.containsKey("Y")` là gì?

**Đáp án:** `10` và `true`. Bản sao không phản ánh các thay đổi của nguồn sau lúc tạo.

**Câu B.** Trong các biểu thức dưới đây, biểu thức nào thay đổi map thành công?

~~~java
// copy.put("Z", 30);
// copy.remove("X");
// copy.replace("X", 50);
// copy.merge("X", 5, Integer::sum);
// copy.keySet().remove("X");
// copy.entrySet().iterator().next().setValue(0);
~~~

**Đáp án:** Không có thao tác cập nhật nào được phép. Khi thực thi trên map do `Map.copyOf` trả về, các thao tác thử này bị từ chối; không được dùng chúng để chỉnh sửa snapshot.

**Câu C.** Muốn kết quả mới có `"X" -> 99`, `"Z" -> 30` và không còn `"Y"`, làm thế nào?

~~~java
var editable = new java.util.HashMap<>(copy);
editable.put("X", 99);
editable.put("Z", 30);
editable.remove("Y");

var updated = java.util.Map.copyOf(editable);
~~~

**Đáp án:** Dùng map mutable tách biệt và gọi `Map.copyOf` để công bố bản mới. Biến `copy` không bị sửa.

## 15. Tổng kết

- `Map.copyOf` (**Java 10+**) trả về **map không sửa được**.
- **`put`, `putAll`, `putIfAbsent`, `remove`, `clear`, `replace`, `replaceAll`, `compute`, `computeIfAbsent`, `computeIfPresent` và `merge`** không dùng được để cập nhật bản sao.
- Không thể lách giới hạn bằng `entrySet().iterator().next().setValue(...)`, `keySet().remove(...)` hay `values().remove(...)`.
- Các lời gọi **đọc** như `get`, `containsKey`, `size`, `forEach` vẫn hợp lệ.
- **Sửa nguồn sau lúc copy** không làm các ánh xạ trong snapshot thay đổi. **Sửa trạng thái của khóa hoặc giá trị mutable** là chuyện khác vì đây là sao chép nông.
- Khi cần cập nhật, hãy **tạo một map mutable mới, sửa nó, rồi gọi `Map.copyOf` lần nữa** để tạo snapshot mới.

### Tham khảo chính thức

- [Java SE 26 — `Map.copyOf(Map)` và Unmodifiable Maps](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): hợp đồng không sửa được, ngoại lệ của mutator và snapshot.
- [Java SE 26 — `Map.Entry.setValue`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.Entry.html#setValue(V)): API thay giá trị và ngoại lệ khi không được hỗ trợ.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn sử dụng factory và bản sao không sửa được.
