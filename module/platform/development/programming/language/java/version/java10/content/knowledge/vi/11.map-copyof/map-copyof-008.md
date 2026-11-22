# Tính chỉ đọc của `keySet()`, `values()` và `entrySet()` trên `Map.copyOf`

## Mục tiêu

Trong Java 10 trở lên, `Map.copyOf(source)` trả về một **Map không cho sửa** (*unmodifiable Map*). Điều này không chỉ ngăn `put`, `remove` hoặc `clear` trên chính Map: ba tập hợp/collection lấy ra từ kết quả qua `keySet()`, `values()` và `entrySet()` cũng **không cho sửa**. Đặc biệt, các đối tượng `Map.Entry` thu được từ `entrySet()` không cho thay giá trị bằng `setValue()`.

Sau bài này, bạn sẽ:

- Biết kiểu trả về và ý nghĩa của từng view: `Set<K>`, `Collection<V>` và `Set<Map.Entry<K,V>>`.
- Phân biệt các thao tác **đọc được phép** với các thao tác **sửa bị từ chối**.
- Hiểu vì sao không thể sửa `Map.copyOf` bằng đường vòng qua `Iterator` hoặc `Map.Entry.setValue`.
- Phân biệt view của `Map.copyOf` với các view trên `HashMap` có thể sửa, cũng như `Collections.unmodifiableMap` dựa trên nguồn.
- Hiểu snapshot ánh xạ khác với bản sao sâu của các đối tượng làm khóa hoặc giá trị.
- Chạy chương trình Java 17+ có kết quả xác định, không phụ thuộc thứ tự duyệt của Map.

> Đây là các API chuẩn vẫn có hiệu lực trong Java hiện đại. `Map.copyOf` được đưa vào Java 10; ví dụ dùng JDK 17 trở lên.

## 1. Bắt đầu từ Map kết quả của `copyOf`

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("An", 9);
source.put("Binh", 8);

Map<String, Integer> snapshot = Map.copyOf(source);
~~~

`snapshot` là một `Map<String, Integer>` có các ánh xạ tại thời điểm gọi và **không hỗ trợ các thao tác sửa nội dung Map**. Ví dụ:

~~~java
// Các thao tác dưới đây sẽ ném UnsupportedOperationException:
// snapshot.put("Chi", 10);
// snapshot.remove("An");
// snapshot.clear();
~~~

Ngoài những lời gọi trực tiếp trên Map, Java còn cho phép đọc dữ liệu qua:

~~~java
Set<String> keys = snapshot.keySet();
Collection<Integer> scores = snapshot.values();
Set<Map.Entry<String, Integer>> entries = snapshot.entrySet();
~~~

Cả ba đều là các **view của Map kết quả**. Chúng không phải những collection mutable riêng biệt có thể dùng để “đi vòng” qua giới hạn của `Map.copyOf`.

Lưu ý thuật ngữ:

- **Unmodifiable Map:** Map không hỗ trợ thao tác làm thay đổi tập ánh xạ qua API của nó.
- **View:** đối tượng đại diện cho khóa, giá trị hoặc entry của một Map. View được liên kết với **Map chứa nó**.
- **Snapshot từ `copyOf`:** nội dung ánh xạ của Map kết quả không phản ánh những lần sửa cấu trúc hoặc thay ánh xạ trên Map nguồn sau thời điểm copy.
- **Không phải deep copy:** đối tượng làm key hoặc value vẫn có thể thay đổi trạng thái nếu bản thân chúng mutable.

## 2. Ba view trả về kiểu gì?

| Phương thức | Kiểu trả về khi Map là `Map<K,V>` | Nội dung biểu diễn |
| --- | --- | --- |
| `keySet()` | `Set<K>` | Các **khóa duy nhất** của Map |
| `values()` | `Collection<V>` | Toàn bộ **giá trị** của các ánh xạ; có thể trùng |
| `entrySet()` | `Set<Map.Entry<K,V>>` | Các cặp khóa/giá trị (entry) |

Ví dụ với nguồn có hai khóa mang cùng giá trị:

~~~java
var source = new HashMap<String, Integer>();
source.put("An", 9);
source.put("Binh", 9);
source.put("Chi", 7);

var snapshot = Map.copyOf(source);

System.out.println(snapshot.keySet().size()); // 3
System.out.println(snapshot.values().size()); // 3
System.out.println(snapshot.entrySet().size()); // 3
~~~

`values()` là **`Collection<V>`**, không phải `Set<V>`. Hai entry `"An" -> 9` và `"Binh" -> 9` đều góp một phần tử `9` vào view các giá trị; giá trị trùng không tự biến mất.

Các view vẫn hỗ trợ các thao tác **đọc** phù hợp như:

- `size()`, `isEmpty()`, `contains(...)` với đối số hợp lệ.
- Duyệt bằng enhanced `for`, `Iterator` hoặc `stream()`.
- Truy xuất `entry.getKey()`, `entry.getValue()` từ từng `Map.Entry`.
- Các phép tổng hợp như `count()`, `filter(...)` trên stream; chúng không sửa collection gốc.

Tuy nhiên, **thứ tự duyệt `Map.copyOf` không được bảo đảm**. Không viết test hoặc logic phụ thuộc vào thứ tự của `keySet()`, `values()`, `entrySet()` hay `toString()` trên Map kết quả.

## 3. Những thao tác nào bị cấm?

### 3.1. `keySet()` không cho xóa khóa

Với Map mutable như `HashMap`, `keySet().remove(key)` có thể xóa ánh xạ tương ứng. Nhưng với `Map.copyOf`:

~~~java
var snapshot = Map.copyOf(Map.of("An", 9));

// snapshot.keySet().remove("An");
// Ném UnsupportedOperationException.
~~~

`keySet()` vẫn có thể đọc tên khóa bằng `contains` hoặc lặp, nhưng không thể sửa Map gián tiếp.

### 3.2. `values()` không cho xóa giá trị

~~~java
var snapshot = Map.copyOf(Map.of("An", 9));

// snapshot.values().remove(9);
// Ném UnsupportedOperationException.
~~~

Việc nhiều khóa cùng có một giá trị không làm thay đổi quy tắc này. `values()` cho phép **đọc cả các giá trị trùng**, nhưng không cho loại bỏ giá trị để xóa ánh xạ.

### 3.3. `entrySet()` không cho xóa entry

~~~java
var snapshot = Map.copyOf(Map.of("An", 9));

// snapshot.entrySet().remove(Map.entry("An", 9));
// Ném UnsupportedOperationException.
~~~

Tập entry có thể dùng để duyệt và phân tích dữ liệu, nhưng không cho xóa entry thông qua `remove` hoặc những thao tác sửa tương tự.

### 3.4. `Map.Entry.setValue()` cũng bị chặn

`Map.Entry<K,V>` có phương thức `setValue(V)`, nhưng **không phải entry nào cũng cho phép gọi thành công**. Những entry do `entrySet()` của Map tạo bởi `Map.copyOf` cung cấp là **không cho sửa**:

~~~java
var snapshot = Map.copyOf(Map.of("An", 9));
var entry = snapshot.entrySet().iterator().next();

System.out.println(entry.getKey());   // An
System.out.println(entry.getValue()); // 9
// entry.setValue(10);                // UnsupportedOperationException
~~~

Đây là điểm quan trọng: chỉ cấm sửa chính Map nhưng lại cho `entry.setValue` hoạt động thì nội dung Map vẫn có thể bị thay đổi. Vì vậy `Map.copyOf` phải chặn cả con đường này.

### 3.5. `Iterator.remove()` cũng không phải lối thoát

~~~java
var snapshot = Map.copyOf(Map.of("An", 9));
var iterator = snapshot.keySet().iterator();

iterator.next();
// iterator.remove(); // UnsupportedOperationException
~~~

Tương tự, iterator qua `values()` hoặc `entrySet()` không cho xóa phần tử khỏi Map kết quả. Với các phương thức sửa hàng loạt như `clear()` hay `removeIf(...)`, không nên dựa vào khả năng sửa của view: các view của `Map.copyOf` là unmodifiable. Một thao tác không thực sự làm thay đổi gì có thể có chi tiết xử lý phụ thuộc phương thức, nên không dùng “thử xóa một phần tử không tồn tại” làm bài kiểm tra bất biến.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu vào file **MapCopyOfViewsDemo.java**:

~~~java
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class MapCopyOfViewsDemo {
    private static void rejected(String label, Runnable change) {
        try {
            change.run();
            System.out.println(label + ": allowed");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashMap<String, Integer>();
        source.put("An", 9);
        source.put("Binh", 9);
        source.put("Chi", 7);

        Map<String, Integer> snapshot = Map.copyOf(source);
        Set<String> keys = snapshot.keySet();
        Collection<Integer> values = snapshot.values();
        Set<Map.Entry<String, Integer>> entries = snapshot.entrySet();

        System.out.println("keys size: " + keys.size());
        System.out.println("keys has An: " + keys.contains("An"));
        System.out.println("values size: " + values.size());
        System.out.println(
                "values with 9: "
                        + values.stream().filter(n -> n == 9).count()
        );

        var entryAn = entries.stream()
                .filter(e -> "An".equals(e.getKey()))
                .findFirst()
                .orElseThrow();
        System.out.println("entry An: " + entryAn.getValue());

        rejected("keySet.remove", () -> keys.remove("An"));
        rejected("values.remove", () -> values.remove(9));
        rejected(
                "entrySet.remove",
                () -> entries.remove(Map.entry("Chi", 7))
        );
        rejected("entry.setValue", () -> entryAn.setValue(5));
        rejected("iterator.remove", () -> {
            var it = keys.iterator();
            it.next();
            it.remove();
        });

        // Sau khi copy, thay đổi Map nguồn.
        source.put("An", 10);
        source.remove("Chi");
        source.put("Duong", 8);

        System.out.println("source size: " + source.size());
        System.out.println("source An: " + source.get("An"));
        System.out.println("snapshot size: " + snapshot.size());
        System.out.println("snapshot An: " + snapshot.get("An"));
        System.out.println("snapshot has Chi: " + keys.contains("Chi"));
        System.out.println("snapshot has Duong: " + keys.contains("Duong"));
        System.out.println("source has Duong: " + source.keySet().contains("Duong"));

        // View keySet() của Map nguồn mutable cho phép xóa ánh xạ.
        source.keySet().remove("Binh");
        System.out.println("source has Binh: " + source.containsKey("Binh"));
        System.out.println("snapshot has Binh: " + snapshot.containsKey("Binh"));

        // View chỉ đọc không bảo vệ trạng thái object mutable bên trong.
        var builder = new StringBuilder("raw");
        var mutableSource = new HashMap<String, StringBuilder>();
        mutableSource.put("note", builder);
        var mutableSnapshot = Map.copyOf(mutableSource);
        builder.append("-changed");
        System.out.println("mutable value: " + mutableSnapshot.get("note"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MapCopyOfViewsDemo.java
java MapCopyOfViewsDemo
~~~

Kết quả chuẩn:

~~~text
keys size: 3
keys has An: true
values size: 3
values with 9: 2
entry An: 9
keySet.remove: UnsupportedOperationException
values.remove: UnsupportedOperationException
entrySet.remove: UnsupportedOperationException
entry.setValue: UnsupportedOperationException
iterator.remove: UnsupportedOperationException
source size: 3
source An: 10
snapshot size: 3
snapshot An: 9
snapshot has Chi: true
snapshot has Duong: false
source has Duong: true
source has Binh: false
snapshot has Binh: true
mutable value: raw-changed
~~~

**Vì sao kết quả không phụ thuộc thứ tự duyệt?** Chương trình chỉ kiểm tra số lượng, membership và tìm entry theo **khóa `"An"`**, không gọi `iterator().next()` để chọn entry bất kỳ rồi in khóa/giá trị (ngoại trừ phần thử `remove`, nơi không in ra phần tử vừa lấy). Giá trị `9` xuất hiện hai lần, do hai khóa khác nhau trỏ tới cùng giá trị số nguyên.

Phương thức `rejected` bắt ngoại lệ `UnsupportedOperationException` của từng thao tác. Nếu một thay đổi bất ngờ thành công, chương trình sẽ in `allowed` để lộ lỗi kỳ vọng; khi chạy với Map do `copyOf` tạo, năm thao tác trong ví dụ đều bị từ chối.

## 5. View của `Map.copyOf` khác view của `HashMap` như thế nào?

Các phương thức `keySet`, `values` và `entrySet` tồn tại trên interface `Map`, nhưng **không có nghĩa mọi Map trả về các view chỉ đọc**. Khả năng sửa phụ thuộc vào Map cụ thể đang được sử dụng.

### View của `HashMap` hoặc `LinkedHashMap` mutable

~~~java
var source = new HashMap<String, Integer>();
source.put("An", 9);
source.put("Binh", 8);

var keys = source.keySet();
keys.remove("An");

System.out.println(source.containsKey("An")); // false
~~~

`keys` là view sống trên chính `source`. `keys.remove("An")` xóa ánh xạ trong Map gốc. Tương tự, view `values()` và `entrySet()` từ các Map mutable thông dụng thường hỗ trợ việc xóa phần tử/entry theo hợp đồng của implementation.

Với `HashMap`, `entrySet()` cung cấp entry gắn với Map, nên `entry.setValue(newValue)` cũng có thể thay ánh xạ trong nguồn. Không áp dụng kết luận này cho `Map.copyOf` vì các entry của nó là unmodifiable.

### View của kết quả `Map.copyOf`

~~~java
var source = new HashMap<String, Integer>();
source.put("An", 9);

var snapshot = Map.copyOf(source);
var keys = snapshot.keySet();

// keys.remove("An"); // UnsupportedOperationException

source.put("Binh", 8);
System.out.println(keys.contains("Binh")); // false
~~~

`keys` là view trên **snapshot**, không phải view trên `source`. Vì Map kết quả không thay đổi ánh xạ theo những lần sửa `source`, view của nó cũng không thấy ánh xạ `"Binh"` được thêm vào nguồn sau thời điểm copy.

## 6. So sánh với `Collections.unmodifiableMap`

`Collections.unmodifiableMap(source)` là một API hiện hành khác, nhưng thường tạo **view không cho sửa dựa trên nguồn**. Nếu có tham chiếu khác sửa nguồn, view vẫn thấy thay đổi:

~~~java
var source = new HashMap<String, Integer>();
source.put("An", 9);

var readOnlyView = java.util.Collections.unmodifiableMap(source);
var snapshot = Map.copyOf(source);

source.put("Binh", 8);

System.out.println(readOnlyView.keySet().contains("Binh")); // true
System.out.println(snapshot.keySet().contains("Binh"));     // false
~~~

Cả `readOnlyView.keySet()` và `snapshot.keySet()` đều không cho sửa qua chính view. **Điểm khác là view đầu tiên quan sát Map nguồn mutable, còn view thứ hai quan sát Map kết quả của `copyOf`.**

| Cách tạo | Sửa qua `keySet/values/entrySet`? | Sau khi sửa Map nguồn qua tham chiếu khác? |
| --- | --- | --- |
| `source.keySet()` từ `HashMap` mutable | Có thể xóa ánh xạ | View thấy thay đổi nguồn |
| `Collections.unmodifiableMap(source).keySet()` | Không cho sửa | View có thể thấy thay đổi nguồn |
| `Map.copyOf(source).keySet()` | Không cho sửa | Không phản ánh thay đổi ánh xạ nguồn về sau |

`Collections.unmodifiableMap` không phải API lỗi thời. Chọn nó khi **cần view luôn phản ánh nguồn**, và chọn `Map.copyOf` khi **cần Map kết quả không phụ thuộc việc nguồn sửa ánh xạ về sau**.

## 7. Đọc an toàn qua từng view

### 7.1. Duyệt các khóa

~~~java
Map<String, Integer> scores = Map.copyOf(Map.of("An", 9, "Binh", 8));

for (var name : scores.keySet()) {
    System.out.println(name);
}
~~~

`name` có kiểu tĩnh `String`. Vòng lặp hợp lệ, nhưng **thứ tự in `An` và `Binh` không được bảo đảm**; đừng dự đoán stdout theo thứ tự nếu ví dụ có hơn một khóa.

### 7.2. Tổng hợp các giá trị

~~~java
Map<String, Integer> scores = Map.copyOf(Map.of("An", 9, "Binh", 9));
int total = scores.values().stream().mapToInt(Integer::intValue).sum();

System.out.println(total); // 18
~~~

`values()` chứa cả hai giá trị `9`, vì vậy tổng là 18. Đây là thao tác **đọc/tính toán**; không thay đổi Map. Không được tự thay `values()` bằng `Set.copyOf(scores.values())` nếu nghiệp vụ yêu cầu giữ số lần xuất hiện của mỗi giá trị: chuyển thành Set sẽ loại các giá trị trùng.

### 7.3. Phân tích các cặp khóa/giá trị

~~~java
Map<String, Integer> scores = Map.copyOf(Map.of("An", 9, "Binh", 8));

var scoreOfAn = scores.entrySet().stream()
        .filter(e -> "An".equals(e.getKey()))
        .map(Map.Entry::getValue)
        .findFirst()
        .orElseThrow();

System.out.println(scoreOfAn); // 9
~~~

`entrySet()` cho phép `getKey()` và `getValue()`. Nó phù hợp khi cần xét **cả khóa lẫn giá trị** trong một lần duyệt. Mặc dù `Map.Entry` có tên phương thức `setValue`, entry của Map từ `copyOf` không hỗ trợ sửa.

Nếu chỉ cần giá trị theo một khóa cụ thể, sử dụng trực tiếp `scores.get("An")` thường rõ và hiệu quả hơn việc duyệt toàn bộ entry.

## 8. “Chỉ đọc” không có nghĩa các object bên trong bất biến

Map không cho sửa ngăn thay đổi **cặp ánh xạ** bằng API Map hoặc view. Nhưng nếu giá trị là một đối tượng mutable, tham chiếu tới nó vẫn cho phép thay đổi **trạng thái của đối tượng đó**:

~~~java
var builder = new StringBuilder("raw");
var source = new HashMap<String, StringBuilder>();
source.put("note", builder);

var snapshot = Map.copyOf(source);

builder.append("-changed");
System.out.println(snapshot.get("note")); // raw-changed
~~~

`snapshot.values()` cũng nhìn thấy chính đối tượng `StringBuilder` ấy sau khi nội dung thay đổi. Đó **không phải** là thêm/xóa/thay ánh xạ trong Map; Map vẫn có khóa `"note"` và vẫn trỏ tới cùng một object.

Nếu key mutable có các trường ảnh hưởng đến `equals`/`hashCode`, việc sửa những trường ấy sau khi copy có thể phá vỡ tính đúng đắn của phép tra cứu. Nên ưu tiên key bất biến và dùng immutable value object khi hệ thống yêu cầu dữ liệu ổn định thực sự.

`Map.copyOf` không phải deep clone. Cũng không được dựa vào `==` để kiểm tra bản sao có được cấp phát mới hay không; với nguồn đã không cho sửa phù hợp, `copyOf` có thể tái sử dụng instance.

## 9. Giới hạn khác của `Map.copyOf` vẫn áp dụng

Ngoài tính chỉ đọc, `Map.copyOf` còn có các quy tắc cần nhớ:

- Không chấp nhận **nguồn Map là `null`**.
- Không chấp nhận **khóa `null`** hoặc **giá trị `null`** trong bất kỳ entry nào của nguồn; trường hợp này ném `NullPointerException`.
- Không cam kết **thứ tự duyệt** các entry, kể cả khi nguồn là `LinkedHashMap`.
- Map kết quả không tự sao chép sâu phần tử; các tham chiếu tới object làm key/value vẫn có thể mang trạng thái mutable.
- `Map.copyOf` có thể tái sử dụng Map không cho sửa phù hợp; do đó không xây logic dựa vào **danh tính object**.

Vì cả key và value đều không được là `null`, code có thể an tâm rằng **những giá trị thực sự xuất hiện trong `snapshot.values()` khác `null`**. Tuy nhiên, `snapshot.get(key)` vẫn có thể trả `null` khi **khóa không tồn tại**; không được đồng nhất việc Map cấm giá trị null với việc mọi lời gọi `get` đều có kết quả khác null.

## 10. Những lỗi thường gặp trong code review

| Lỗi hoặc hiểu nhầm | Thực tế | Hướng sửa |
| --- | --- | --- |
| `copy.keySet().remove(k)` để xóa key | View của Map từ `copyOf` không cho sửa | Muốn Map mutable thì dùng `new HashMap<>(copy)` |
| `copy.values().remove(v)` để xóa entry | View `values()` không cho sửa | Thay đổi Map nguồn mutable trước khi tạo snapshot |
| `copy.entrySet().remove(e)` để xóa entry | Entry set không cho sửa | Tạo bản sao mutable rồi thay đổi |
| `copy.entrySet().iterator().next().setValue(v)` | Entry cũng unmodifiable | Dùng `mutable.put(key, value)` trên Map mutable |
| `iterator.remove()` qua view | Iterator không cung cấp đường sửa | Chỉ duyệt/đọc view |
| `values()` được xem là Set | Nhiều khóa có thể có cùng giá trị | Giữ kiểu `Collection<V>` và tôn trọng số lần xuất hiện |
| Nghĩ `keySet()` của mọi Map đều chỉ đọc | View trên `HashMap` thường có thể xóa ánh xạ | Xem implementation và hợp đồng Map |
| Nghĩ mọi unmodifiable view đều là snapshot | `Collections.unmodifiableMap(source)` có thể thấy nguồn thay đổi | Phân biệt view và `Map.copyOf` |
| Dựa vào thứ tự duyệt `entrySet()` | `Map.copyOf` không bảo đảm thứ tự | Sắp xếp rõ ràng nếu cần thứ tự |
| Nghĩ `copyOf` đóng băng object value | Giá trị mutable vẫn thay đổi trạng thái | Sử dụng immutable key/value hoặc sao chép sâu có chủ đích |

Khi cần thay đổi một Map từ `copyOf`, cách thường dùng là tạo **bản sao mutable mới**, cập nhật nó rồi tạo một Map không cho sửa khác:

~~~java
Map<String, Integer> original = Map.copyOf(Map.of("An", 9));

var editable = new HashMap<>(original);
editable.put("Binh", 8);

Map<String, Integer> updated = Map.copyOf(editable);
~~~

`original` vẫn không đổi về mặt ánh xạ; `updated` chứa cả `An` và `Binh`. Đây là cách làm rõ ràng hơn so với cố gắng sửa `keySet`, `values` hoặc `entrySet` của `original`.

## 11. Câu hỏi tự kiểm tra

Cho đoạn mã sau (giả sử đã import các lớp từ `java.util`):

~~~java
var source = new HashMap<String, Integer>();
source.put("A", 1);
source.put("B", 1);

var copy = Map.copyOf(source);
var keys = copy.keySet();
var values = copy.values();
var entries = copy.entrySet();

source.put("C", 3);

// A. keys.contains("C") là true hay false?
// B. values.size() và số lượng giá trị 1 là bao nhiêu?
// C. keys.remove("A") có xóa entry trong copy không?
// D. entries.iterator().next().setValue(5) có hợp lệ không?
// E. source.keySet().remove("A") có thể làm gì?
~~~

**Đáp án:**

1. **A = `false`**. `keys` là view của `copy`, trong khi `"C"` chỉ được thêm vào nguồn sau khi tạo bản sao.
2. **B = 2 phần tử, trong đó giá trị 1 xuất hiện hai lần.** `values()` là Collection, không tự loại giá trị trùng.
3. **C = không**. Lời gọi `keys.remove("A")` ném `UnsupportedOperationException`; `copy` vẫn chứa `"A"`.
4. **D = không**. Entry lấy từ view của Map `copyOf` không cho thay value; `setValue(5)` ném `UnsupportedOperationException`.
5. **E = xóa ánh xạ `"A"` khỏi `source`** nếu nguồn là `HashMap` mutable; `copy` vẫn giữ ánh xạ `"A" -> 1`.

Câu hỏi mở rộng: nếu hai giá trị là cùng một đối tượng mutable thay vì số nguyên, việc sửa nội dung đối tượng ấy có thể được quan sát qua `copy.values()` không? **Có**, vì các object value không được deep copy.

## 12. Tóm tắt và tài liệu tham khảo

Ba phương thức đều cung cấp các góc nhìn **chỉ đọc** trên Map kết quả của `Map.copyOf`:

- **`keySet(): Set<K>`** — đọc tập khóa duy nhất; không sửa Map qua view.
- **`values(): Collection<V>`** — đọc mọi giá trị, kể cả giá trị trùng; không xóa các ánh xạ qua view.
- **`entrySet(): Set<Map.Entry<K,V>>`** — đọc các cặp; không xóa entry hoặc gọi `setValue` để sửa Map.

Các view gắn với **Map không cho sửa do `copyOf` trả về** chứ không gắn với Map nguồn mutable. Sửa ánh xạ của nguồn sau khi copy không thay đổi Map kết quả. Nhưng tham chiếu tới phần tử mutable vẫn cần được quản lý cẩn thận: “unmodifiable” không tương đương “deep immutable”.

Tài liệu chuẩn, áp dụng cho Java 17+:

- [Java SE 17 — `Map`, các phương thức `copyOf`, `keySet`, `values`, `entrySet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [Java SE 17 — `Map.Entry` và `setValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)
- [Java SE 17 — `HashMap` và các backed views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [Java SE 17 — `Collections.unmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map))

**Kết luận:** Với `Map.copyOf`, không chỉ Map chính là chỉ đọc; các view `keySet()`, `values()`, `entrySet()` và những `Map.Entry` mà chúng cung cấp cũng không cho thay đổi ánh xạ. Hãy chọn `copyOf` để tạo ranh giới dữ liệu không cho sửa, và chọn Map mutable khi nghiệp vụ yêu cầu cập nhật.
