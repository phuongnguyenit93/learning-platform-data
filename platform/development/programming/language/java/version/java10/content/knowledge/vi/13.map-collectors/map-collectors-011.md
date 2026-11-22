# Giới hạn thay đổi qua các khung nhìn của Map khi dùng Collector Java 10

## Mục tiêu

Trong Java 10, `Collectors.toUnmodifiableMap(...)` cho phép gom dữ liệu từ Stream thành một `Map` **không cho sửa** (*unmodifiable Map*). Quy tắc này không chỉ áp dụng cho `put()`, `remove()` hay `clear()` trên Map chính: các khung nhìn (*views*) lấy qua `keySet()`, `values()`, `entrySet()` và những đối tượng `Map.Entry` trả về cũng không được dùng để thay đổi các ánh xạ.

Đây là kiến thức vẫn áp dụng trong Java hiện đại. Các ví dụ dùng Java 17 trở lên và thư viện chuẩn.

Sau bài học, bạn có thể:

- Nhận biết `Collectors.toUnmodifiableMap` và loại Map mà nó trả về.
- Phân biệt ba khung nhìn `keySet(): Set<K>`, `values(): Collection<V>`, `entrySet(): Set<Map.Entry<K,V>>`.
- Giải thích vì sao `remove()`, `Iterator.remove()` và `Map.Entry.setValue()` không thể vượt qua tính không cho sửa.
- Phân biệt view từ Map collector với view của `HashMap` mutable, `Collections.unmodifiableMap` và snapshot `Map.copyOf`.
- Nhận biết giới hạn của tính bất biến: phần tử là object mutable hoặc giá trị lồng nhau vẫn có thể đổi trạng thái.
- Xử lý lỗi khóa trùng và `null` khi tạo Map bằng collector, kiểm tra bằng code chạy được.

## 1. Tạo Map không cho sửa bằng collector Java 10

Dùng `Collectors.toUnmodifiableMap` như sau:

~~~java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Đoạn mã minh họa nằm trong một phương thức:
Map<String, Integer> scores = Stream.of("An:9", "Binh:8")
        .collect(Collectors.toUnmodifiableMap(
                row -> row.split(":")[0],
                row -> Integer.parseInt(row.split(":")[1])
        ));
~~~

Trong ví dụ, `scores` chứa ánh xạ `"An" -> 9`, `"Binh" -> 8`. Lời gọi `collect(...)` là terminal operation của Stream; collector tạo ra Map kết quả. Map được trả về không cho phép các phương thức sửa ánh xạ.

Hai overload quan trọng của collector:

~~~java
// Hai hàm ánh xạ, các khóa phải duy nhất:
toUnmodifiableMap(keyMapper, valueMapper)

// Thêm một hàm gộp khi hai phần tử có cùng khóa:
toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
~~~

Các chữ ký generic tương ứng, viết gọn để dễ đọc:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>>
toUnmodifiableMap(Function<? super T, ? extends K> keyMapper,
                  Function<? super T, ? extends U> valueMapper);

static <T, K, U> Collector<T, ?, Map<K, U>>
toUnmodifiableMap(Function<? super T, ? extends K> keyMapper,
                  Function<? super T, ? extends U> valueMapper,
                  BinaryOperator<U> mergeFunction);
~~~

`T` là kiểu phần tử Stream, `K` là kiểu khóa và `U` là kiểu giá trị Map. Kết quả là `Map<K, U>` không cho sửa. Không nên suy luận loại implementation cụ thể như `HashMap` hoặc thứ tự duyệt từ tên phương thức này.

**Trọng tâm bài:** sau khi collector trả về Map, các phương thức truy cập khung nhìn không làm Map ấy trở thành mutable.

## 2. Ba khung nhìn `keySet`, `values`, `entrySet`

Với `Map<K,V> map`:

| Phương thức | Kiểu trả về | Nội dung nhìn thấy | Có thể sửa các ánh xạ của Map collector không? |
| --- | --- | --- | --- |
| `map.keySet()` | `Set<K>` | Tập hợp các khóa duy nhất | **Không** |
| `map.values()` | `Collection<V>` | Các giá trị, **có thể trùng** | **Không** |
| `map.entrySet()` | `Set<Map.Entry<K,V>>` | Tập các cặp khóa–giá trị | **Không** |

Ví dụ:

~~~java
var scores = Stream.of(
        Map.entry("An", 9),
        Map.entry("Binh", 9),
        Map.entry("Chi", 7)
).collect(Collectors.toUnmodifiableMap(
        Map.Entry::getKey,
        Map.Entry::getValue
));

var keys = scores.keySet();     // Set<String>
var values = scores.values();   // Collection<Integer>
var entries = scores.entrySet();// Set<Map.Entry<String, Integer>>

System.out.println(keys.size());   // 3
System.out.println(values.size()); // 3
System.out.println(entries.size());// 3
~~~

Dù `An` và `Binh` có cùng số điểm `9`, `values()` vẫn có ba phần tử. **`values()` không phải `Set<V>`** và không tự loại các giá trị trùng.

Các khung nhìn này vẫn dùng được để **đọc**, ví dụ `size()`, `contains()`, `stream()`, duyệt bằng enhanced `for`, đọc `Map.Entry.getKey()` và `getValue()`. Nhưng chúng không hỗ trợ thay đổi tập ánh xạ.

## 3. Những con đường sửa bị chặn

### 3.1. Sửa Map trực tiếp

~~~java
var result = Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableMap(
                String::toLowerCase,
                String::length
        ));

// result.put("c", 1); // UnsupportedOperationException
// result.remove("a"); // UnsupportedOperationException
// result.clear();     // UnsupportedOperationException
~~~

Với unmodifiable Map, `put`, `remove`, `replace` và các thao tác sửa nội dung không phải con đường hợp lệ.

### 3.2. Sửa qua `keySet()`

~~~java
// result.keySet().remove("a");
// UnsupportedOperationException: không thể xóa khóa để xóa ánh xạ.
~~~

`keySet()` biểu diễn các khóa của Map, không tạo ra một Set có thể sửa độc lập. Với Map collector không cho sửa, việc xóa khóa bị cấm.

### 3.3. Sửa qua `values()`

~~~java
// result.values().remove(1);
// UnsupportedOperationException: không thể xóa ánh xạ thông qua một value.
~~~

`values()` cho phép đọc các giá trị trùng nhau, nhưng không cho phép xóa bớt entry thông qua `remove` hoặc sửa nội dung.

### 3.4. Sửa qua `entrySet()`

~~~java
// result.entrySet().remove(Map.entry("a", 1));
// UnsupportedOperationException.
~~~

`entrySet()` cho phép đọc và duyệt các cặp khóa/giá trị. Nó không phải một collection mutable có thể xóa entry khỏi Map kết quả.

### 3.5. Sửa giá trị bằng `Map.Entry.setValue()`

Ngay cả khi chỉ đọc một entry rồi gọi phương thức trên entry đó, Map vẫn không thay đổi được:

~~~java
var entry = result.entrySet().stream()
        .filter(e -> e.getKey().equals("a"))
        .findFirst()
        .orElseThrow();

// entry.setValue(10); // UnsupportedOperationException
~~~

`Map.Entry` có phương thức `setValue(V)` ở interface, nhưng không có nghĩa mọi đối tượng entry đều hỗ trợ nó. Entry thuộc Map do `toUnmodifiableMap` tạo ra không cho sửa; chỉ có `getKey()` và `getValue()` là các thao tác đọc phù hợp.

### 3.6. Sửa qua Iterator hoặc default methods

~~~java
var iterator = result.keySet().iterator();
iterator.next();
// iterator.remove(); // UnsupportedOperationException
~~~

Các iterator từ `keySet`, `values`, `entrySet` không được dùng để xóa ánh xạ. Tương tự, không thể dùng `removeIf`, `clear`, `replaceAll`, `compute` hoặc `merge` để thay đổi Map collector đã không cho sửa.

**Lưu ý chính xác:** với những lời gọi không gây thay đổi (ví dụ xóa một khóa không tồn tại), chi tiết về việc ném hay không ném ngoại lệ có thể phụ thuộc hợp đồng của từng phương thức; đừng kiểm tra tính bất biến bằng một thao tác *no-op*. Những ví dụ thử lỗi trong chương trình bên dưới đều nhắm vào phần tử có tồn tại và thao tác thay đổi thực sự.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào file **UnmodifiableMapViewDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnmodifiableMapViewDemo {
    record Score(String user, Integer points) {}

    private static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": allowed");
        } catch (UnsupportedOperationException error) {
            System.out.println(label + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        var sourceRows = List.of(
                new Score("an", 9),
                new Score("binh", 9),
                new Score("chi", 7)
        );

        Map<String, Integer> result = sourceRows.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Score::user, Score::points
                ));

        Set<String> keys = result.keySet();
        Collection<Integer> values = result.values();
        Set<Map.Entry<String, Integer>> entries = result.entrySet();

        var entryAn = entries.stream()
                .filter(e -> e.getKey().equals("an"))
                .findFirst()
                .orElseThrow();

        System.out.println("size: " + result.size());
        System.out.println("has an: " + keys.contains("an"));
        System.out.println(
                "score 9 count: "
                        + values.stream().filter(v -> v == 9).count()
        );
        System.out.println("an points: " + entryAn.getValue());

        check("keySet.remove", () -> keys.remove("an"));
        check("values.remove", () -> values.remove(9));
        check(
                "entrySet.remove",
                () -> entries.remove(Map.entry("chi", 7))
        );
        check("entry.setValue", () -> entryAn.setValue(10));
        check("iterator.remove", () -> {
            var iterator = entries.iterator();
            iterator.next();
            iterator.remove();
        });

        var duplicate = List.of(
                new Score("an", 9), new Score("an", 10)
        );

        try {
            duplicate.stream().collect(
                    Collectors.toUnmodifiableMap(
                            Score::user, Score::points
                    )
            );
        } catch (IllegalStateException error) {
            System.out.println("duplicate key: IllegalStateException");
        }

        var merged = duplicate.stream().collect(
                Collectors.toUnmodifiableMap(
                        Score::user, Score::points, Integer::sum
                )
        );
        System.out.println("merged an: " + merged.get("an"));

        try {
            Stream.of(new Score(null, 1)).collect(
                    Collectors.toUnmodifiableMap(
                            Score::user, Score::points
                    )
            );
        } catch (NullPointerException error) {
            System.out.println("null key: NullPointerException");
        }

        try {
            Stream.of(new Score("empty", null)).collect(
                    Collectors.toUnmodifiableMap(
                            Score::user, Score::points
                    )
            );
        } catch (NullPointerException error) {
            System.out.println("null value: NullPointerException");
        }

        var mutable = new LinkedHashMap<String, Integer>();
        mutable.put("old", 1);

        var liveView = Collections.unmodifiableMap(mutable);
        var snapshot = Map.copyOf(mutable);
        mutable.put("new", 2);

        System.out.println(
                "live view new: " + liveView.keySet().contains("new")
        );
        System.out.println(
                "copy new: " + snapshot.keySet().contains("new")
        );

        var bag = new ArrayList<>(List.of("A"));
        var nested = Stream.of(bag).collect(
                Collectors.toUnmodifiableMap(x -> "items", x -> x)
        );
        bag.add("B");
        System.out.println(
                "mutable value size: " + nested.get("items").size()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UnmodifiableMapViewDemo.java
java UnmodifiableMapViewDemo
~~~

Kết quả chuẩn:

~~~text
size: 3
has an: true
score 9 count: 2
an points: 9
keySet.remove: UnsupportedOperationException
values.remove: UnsupportedOperationException
entrySet.remove: UnsupportedOperationException
entry.setValue: UnsupportedOperationException
iterator.remove: UnsupportedOperationException
duplicate key: IllegalStateException
merged an: 19
null key: NullPointerException
null value: NullPointerException
live view new: true
copy new: false
mutable value size: 2
~~~

**Cách đọc kết quả:**

1. Map có ba khóa `an`, `binh`, `chi`; hai giá trị bằng `9` cùng tồn tại trong view `values()`.
2. Các thao tác thử sửa vào phần tử hiện có đều ném `UnsupportedOperationException`. Không có cách sửa Map thông qua `entrySet`, `setValue` hoặc `Iterator.remove`.
3. Hai dòng cùng khóa `"an"` khi dùng overload không có hàm merge sẽ gây `IllegalStateException`. Với `Integer::sum`, hai giá trị `9` và `10` được gộp thành `19`.
4. Trường hợp mapper tạo khóa hoặc giá trị `null` đều gây `NullPointerException`.
5. `Collections.unmodifiableMap(mutable)` là live view trên Map nguồn, còn `Map.copyOf(mutable)` cho kết quả không phản ánh việc thêm khóa mới vào nguồn.
6. Trong `nested`, Map ngoài không cho sửa nhưng giá trị là `ArrayList<String>` mutable; khi `bag` được thêm phần tử, nội dung nhìn qua value tăng kích thước lên 2.

Chương trình **không phụ thuộc thứ tự duyệt của Map**: nó dùng `size`, `contains`, lọc entry theo khóa hoặc lấy giá trị bằng khóa cụ thể, tránh so sánh chuỗi kết quả `Map.toString()`.

## 5. Khác biệt với khung nhìn của Map mutable

Các phương thức `keySet`, `values`, `entrySet` có trên mọi `Map`, nhưng không phải Map nào cũng không cho sửa. Xét `HashMap` mutable:

~~~java
var source = new java.util.HashMap<String, Integer>();
source.put("an", 9);
source.put("binh", 8);

var keys = source.keySet();
keys.remove("an");

System.out.println(source.containsKey("an")); // false
~~~

`keys` là một **view gắn với Map nguồn**. Xóa một khóa qua view có thể xóa ánh xạ của nguồn. Tương tự, `values().remove(value)` và `entrySet().remove(entry)` được hỗ trợ với những phần tử phù hợp theo hợp đồng của `HashMap`.

`HashMap.entrySet()` cũng có thể cung cấp `Map.Entry` mà `setValue` cập nhật ánh xạ, trong khi entry của Map từ `toUnmodifiableMap` không có khả năng này.

Đừng suy ra “`Map.Entry` có `setValue` nghĩa là mọi entry đều mutable”. Hãy xét **nguồn cung cấp entry** và hợp đồng cụ thể của Map.

| Đối tượng nhận được | Có thể đổi ánh xạ qua view? | Có phản ánh Map nguồn đang được sửa không? |
| --- | --- | --- |
| `source.keySet()` từ `HashMap` mutable | Có thể | Có |
| `source.entrySet()` từ `HashMap` mutable | Có thể | Có |
| `Collectors.toUnmodifiableMap(...)` rồi `keySet()` | Không | Không có Map nguồn mutable gắn với result; các ánh xạ đã tạo không cho sửa |
| `Collections.unmodifiableMap(source).keySet()` | Không | Có, qua nguồn mutable |
| `Map.copyOf(source).keySet()` | Không | Không phản ánh thay đổi ánh xạ sau khi copy |

## 6. So sánh với `Collections.unmodifiableMap` và `Map.copyOf`

### 6.1. `Collections.unmodifiableMap`: view không cho sửa

~~~java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("A", 1);

var view = java.util.Collections.unmodifiableMap(source);
source.put("B", 2);

System.out.println(view.keySet().contains("B")); // true
~~~

Không thể dùng `view.keySet().remove("A")`, nhưng `view` vẫn phản ánh thao tác `source.put("B",2)`. Đó là một **view không cho sửa**, không phải bản sao độc lập.

### 6.2. `Map.copyOf`: snapshot không cho sửa từ nguồn

~~~java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("A", 1);

var snapshot = Map.copyOf(source);
source.put("B", 2);

System.out.println(snapshot.keySet().contains("B")); // false
~~~

`Map.copyOf`, cũng có từ Java 10, tạo unmodifiable Map mang các ánh xạ khi copy. View của bản sao không phản ánh thay đổi ánh xạ của nguồn về sau.

### 6.3. `Collectors.toUnmodifiableMap`: xây Map từ Stream

~~~java
var map = Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableMap(
                x -> x, String::length
        ));
~~~

Ở đây không cần tạo một Map mutable trước rồi bọc hay copy. Collector trực tiếp gom từ dữ liệu Stream. Kết quả có thuộc tính không cho sửa tương tự về **khả năng sửa các khung nhìn**, nhưng đường tạo dữ liệu khác.

**Lựa chọn:** nếu dữ liệu đang ở dạng `Stream<T>`, `toUnmodifiableMap` là công cụ phù hợp; nếu đã có `Map<K,V>` cần snapshot, `Map.copyOf` trực tiếp rõ mục đích; nếu cố ý muốn read-only view phản ánh Map mutable, `Collections.unmodifiableMap` vẫn là API được hỗ trợ và có ích.

## 7. Khóa trùng và `null`: xử lý ngay khi collect

Giới hạn của collector thể hiện **trước** lúc bạn nhận được Map để gọi `keySet`/ `values`/ `entrySet`.

### 7.1. Trùng khóa với overload hai tham số

~~~java
record Score(String user, int points) {}

var source = List.of(
        new Score("an", 9),
        new Score("an", 10)
);

// Ném IllegalStateException do khóa "an" bị lặp:
// source.stream().collect(Collectors.toUnmodifiableMap(
//         Score::user, Score::points
// ));
~~~

Nếu trùng khóa là lỗi dữ liệu, overload hai tham số giúp phát hiện; nếu có quy tắc gộp phù hợp, dùng overload có `mergeFunction`:

~~~java
var merged = source.stream().collect(
        Collectors.toUnmodifiableMap(
                Score::user,
                Score::points,
                Integer::sum
        )
);

System.out.println(merged.get("an")); // 19
~~~

Kết quả sau merge vẫn là **Map không cho sửa**. Hàm merge phải được lựa chọn theo nghiệp vụ; không nên tự động dùng “giữ giá trị cuối” nếu không có lý do rõ ràng, đặc biệt trong pipeline có thể xử lý song song.

### 7.2. Khóa và giá trị `null`

`Collectors.toUnmodifiableMap` cấm cả **khóa `null`** lẫn **giá trị `null`**. Nếu `keyMapper` hoặc `valueMapper` tạo `null`, quá trình thu thập ném `NullPointerException`, không trả về Map chứa một phần dữ liệu.

~~~java
// Cố ý minh họa lỗi runtime:
record Pair(String key, Integer value) {}

var source = List.of(
        new Pair("A", 1),
        new Pair("B", null)
);

// source.stream().collect(Collectors.toUnmodifiableMap(
//         Pair::key, Pair::value
// )); // NullPointerException do một value null
~~~

Để bảo đảm đầu ra đúng hợp đồng, cần **xác thực hoặc lọc đầu vào trước khi collect** khi nghiệp vụ cho phép. Tránh biến `null` thành dữ liệu giả chỉ để né ngoại lệ, vì điều đó có thể làm mất ý nghĩa dữ liệu gốc.

Các factory `Map.of`, `Map.ofEntries` và `Map.copyOf` cũng cấm `null`, nhưng bạn không nên đồng nhất chúng với collector: chúng nhận **các đối số hoặc Map khác nhau**.

## 8. Thứ tự duyệt và số lần xuất hiện của value

**Không có thứ tự duyệt được cam kết** cho Map được thu bằng `Collectors.toUnmodifiableMap`. Nếu Stream nguồn có thứ tự, điều đó không đồng nghĩa Map kết quả duyệt entry theo cùng thứ tự. Tránh kiểm thử `result.toString()` như thể nó luôn in khóa theo thứ tự đầu vào.

Khi cần hiển thị có thứ tự, bạn có thể lấy các entry, sắp xếp rồi tạo một danh sách phục vụ việc hiển thị:

~~~java
var result = Stream.of("B", "A")
        .collect(Collectors.toUnmodifiableMap(
                x -> x, String::length
        ));

var sorted = result.entrySet().stream()
        .sorted(Map.Entry.comparingByKey())
        .toList();

System.out.println(sorted.get(0).getKey()); // A
~~~

`Stream.toList()` có từ Java 16 và trả về List không cho sửa. Đây chỉ là **List hiển thị đã sắp xếp**, không phải một thay đổi đối với Map gốc.

Ngược lại, **giá trị trùng nhau vẫn xuất hiện nhiều lần trong `values()`** nếu có nhiều khóa khác nhau cùng trỏ tới chúng. `values()` là `Collection<V>`, không phải Set. Nếu cần đếm số bản ghi có một value, bạn có thể dùng `values().stream().filter(...).count()` mà không thay đổi Map.

## 9. “Chỉ đọc” không đồng nghĩa bất biến sâu

Giả sử value là một danh sách mutable:

~~~java
var items = new java.util.ArrayList<>(List.of("A"));
var result = Stream.of(items).collect(
        Collectors.toUnmodifiableMap(x -> "items", x -> x)
);

items.add("B");

System.out.println(result.get("items").size()); // 2
~~~

Bản thân `result.put(...)` và thao tác sửa qua view bị cấm, nhưng `result.get("items")` vẫn tham chiếu đến **cùng `ArrayList` có thể sửa**. Nếu lấy value qua `result.values()`, code vẫn có thể gọi phương thức trên object value để làm thay đổi **object bên trong**, miễn không sửa tập ánh xạ của Map.

Vì vậy:

- Unmodifiable Map bảo vệ **cấu trúc ánh xạ**, không tự nhân bản sâu key/value.
- Nếu value là object mutable, thay đổi trạng thái ngoài Map vẫn có thể nhìn thấy.
- Nếu key mutable và `equals`/`hashCode` phụ thuộc trạng thái có thể đổi, thay đổi key có thể làm việc tra cứu không còn đúng.
- Khi cần giá trị thật sự bất biến, dùng immutable value object hoặc thực hiện copy có chủ đích của các object trước khi thu thập.

Đặc biệt với các collector lồng nhau, cần xét **mỗi tầng**. Ví dụ, `groupingBy(..., toUnmodifiableMap(...))` có thể tạo List/Map con không cho sửa nhưng Map nhóm bên ngoài vẫn theo hợp đồng của `groupingBy`. Một tầng không cho sửa không tự động làm mọi container bao quanh hay object bên trong trở thành bất biến.

## 10. Quy trình chọn cách làm trong ứng dụng

| Nhu cầu | Cách làm nên cân nhắc | Lý do |
| --- | --- | --- |
| Đang có Stream, muốn Map không cho sửa | `collect(Collectors.toUnmodifiableMap(k, v))` | Tạo trực tiếp Map từ Stream |
| Có khóa trùng và có quy tắc gộp rõ ràng | `toUnmodifiableMap(k, v, merge)` | Giải quyết trùng theo logic nghiệp vụ |
| Có Map mutable đã tồn tại, muốn snapshot | `Map.copyOf(source)` | Bản sao ánh xạ không phản ánh sửa nguồn về sau |
| Cần view không cho sửa nhưng thấy nguồn thay đổi | `Collections.unmodifiableMap(source)` | Backed view trên nguồn |
| Cần Map có thể thêm/xóa/sửa sau khi thu thập | `collect(Collectors.toMap(k,v,merge, LinkedHashMap::new))` | Chỉ rõ loại Map mutable muốn tạo |
| Cần sửa một Map đã được tạo không cho sửa | `new HashMap<>(result)` rồi cập nhật | Không cố sửa qua view |
| Cần thứ tự khóa để hiển thị | `entrySet().stream().sorted(...).toList()` | Không phụ thuộc iteration order của Map collector |
| Cần ràng buộc tính bất biến của value bên trong | Value object bất biến hoặc copy từng value | Unmodifiable Map không phải deep copy |

Ví dụ “tạo bản mới để cập nhật”:

~~~java
var collected = Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableMap(
                x -> x, String::length
        ));

var editable = new java.util.HashMap<>(collected);
editable.put("C", 1);

var updated = Map.copyOf(editable);
~~~

`collected` vẫn giữ hai ánh xạ ban đầu; `updated` chứa ba ánh xạ. Không có thao tác nào sửa trực tiếp các khung nhìn của `collected`.

`Collectors.toMap` cũng là API còn áp dụng, nhưng overload không chỉ rõ loại Map **không cam kết** tính sửa được hay implementation cụ thể của kết quả. Nếu cần chắc chắn có `LinkedHashMap` mutable, hãy cung cấp `mapFactory` tường minh như ví dụ trong bảng.

## 11. Những lỗi thường gặp

**Lỗi 1 — Nghĩ `entrySet()` có thể lách unmodifiable:** entry của Map collector không hỗ trợ `setValue()`. Không dùng chúng để cập nhật Map.

**Lỗi 2 — Nghĩ `values()` là Set:** nhiều khóa có thể có cùng value; `values()` có kiểu `Collection<V>`, nên việc đếm số phần tử giữ số lần xuất hiện.

**Lỗi 3 — Nghĩ mọi `Map.keySet()` đều chỉ đọc:** view từ `HashMap` mutable cho phép thao tác xóa phù hợp; cần xét Map gốc.

**Lỗi 4 — Nghĩ `Collections.unmodifiableMap(source)` là snapshot:** đây là view; Map nguồn thay đổi qua tham chiếu khác thì view cũng thấy.

**Lỗi 5 — Nghĩ `toUnmodifiableMap` chấp nhận khóa trùng:** overload hai mapper sẽ ném `IllegalStateException`. Chỉ dùng merge function nếu có chính sách gộp rõ ràng.

**Lỗi 6 — Nghĩ `null` tự bị bỏ qua:** collector cấm `null` ở key và value; cần xác thực dữ liệu.

**Lỗi 7 — Dựa vào thứ tự duyệt của Map:** Map collector không cam kết thứ tự; hãy sắp xếp riêng.

**Lỗi 8 — Nhầm không cho sửa Map với đóng băng object value:** object mutable bên trong vẫn có thể thay đổi. Cần thiết kế thêm nếu muốn bất biến sâu.

**Lỗi 9 — Dùng `Collectors.toMap` như một cam kết `HashMap` có thể sửa:** khi cần implementation rõ ràng, sử dụng overload `toMap` có `mapFactory`, không dựa vào quan sát ở một JDK.

## 12. Bài tập tự kiểm tra

Giả sử đã import `java.util.*` và `java.util.stream.*`, hãy dự đoán câu trả lời:

~~~java
var map = Stream.of("A:5", "B:5", "C:8")
        .collect(Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2))
        ));

var keys = map.keySet();
var values = map.values();
var entries = map.entrySet();

// 1. keys.size() là bao nhiêu?
// 2. Có bao nhiêu phần tử bằng 5 trong values?
// 3. keys.remove("A") có sửa map không?
// 4. values.remove(5) có sửa map không?
// 5. entrySet().iterator().next().setValue(0) có được phép?
// 6. Có thể đoán chắc thứ tự duyệt keys không?
~~~

**Đáp án:**

1. `keys.size() == 3`, vì có ba khóa riêng biệt.
2. Hai phần tử bằng `5`, vì `A` và `B` có cùng value.
3. Không. `keys.remove("A")` ném `UnsupportedOperationException`.
4. Không. `values.remove(5)` ném `UnsupportedOperationException`.
5. Không. Entry của Map không cho sửa; `setValue(0)` ném `UnsupportedOperationException`.
6. Không. `toUnmodifiableMap` không cam kết iteration order.

**Câu hỏi mở rộng:** Nếu value là `ArrayList<String>`, có thể gọi `map.get(key).add(...)` hay không? Câu trả lời phụ thuộc vào việc List **value** có mutable không. Map không cho sửa **không tự ngăn** thay đổi trạng thái của object làm value.

## 13. Ghi nhớ và tài liệu chuẩn

- Java 10 có **`Collectors.toUnmodifiableMap`**, dùng để tạo Map không cho sửa từ Stream.
- `keySet()`, `values()`, `entrySet()` của kết quả đều chỉ dùng để **đọc**, không cho sửa ánh xạ.
- `Map.Entry.setValue()`, `Iterator.remove()`, `keySet.remove()`, `values.remove()` và `entrySet.remove()` không thể cập nhật Map kết quả.
- `values()` có thể chứa nhiều bản sao của một giá trị vì nhiều khóa có thể trỏ tới cùng value.
- Collector cấm key/value `null`; overload hai mapper báo lỗi khi trùng khóa, overload ba tham số cho phép gộp theo quy tắc được chỉ định.
- Unmodifiable Map không phải deep copy; mutable key/value vẫn cần được kiểm soát.
- Phân biệt Map được collector tạo ra, Map snapshot qua `Map.copyOf` và live view qua `Collections.unmodifiableMap`.

Tài liệu chính thức (Java 17+, các API vẫn được hỗ trợ):

- [Java SE 17 — `Collectors.toUnmodifiableMap` và `Collectors.toMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 17 — `Map.keySet`, `Map.values`, `Map.entrySet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [Java SE 17 — `Map.Entry` và `setValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)
- [Java SE 17 — `Collections.unmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map))

**Kết luận:** Khi một Stream được thu thập bằng `Collectors.toUnmodifiableMap`, mọi đường sửa ánh xạ qua Map và qua các khung nhìn `keySet`, `values`, `entrySet` đều bị chặn. Hãy chọn collector đúng hợp đồng và phân biệt rõ tính không cho sửa của **Map** với khả năng đổi trạng thái của **object** mà Map tham chiếu.
