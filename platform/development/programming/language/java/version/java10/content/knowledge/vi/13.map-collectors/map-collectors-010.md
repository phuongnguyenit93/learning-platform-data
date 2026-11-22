# So sánh `Collectors.toUnmodifiableMap` với `Collectors.toMap` và `toConcurrentMap`

**Chủ đề:** Collector bản đồ — Java 10 trở lên.

Khi cần biến `Stream<T>` thành `Map<K,V>`, Java có ba nhóm collector dễ bị nhầm: `Collectors.toMap(...)`, `Collectors.toConcurrentMap(...)` và `Collectors.toUnmodifiableMap(...)`. Chúng đều nhận hàm tạo khóa và giá trị, đều phải xử lý **khóa trùng**, nhưng khác nhau đáng kể ở **khả năng sửa kết quả**, **đặc tính concurrent/unordered**, **cách lựa chọn implementation** và **quy tắc null**.

`toUnmodifiableMap` xuất hiện trong Java 10 và vẫn là API hiện hành; `toMap`/`toConcurrentMap` cũng tiếp tục được dùng. Bài này tập trung vào các quy tắc còn áp dụng trong Java hiện đại. Bốn chương trình đầy đủ bên dưới đã được kiểm tra với `javac --release 10`; không cần dependency ngoài JDK.

## 1. Mô hình tư duy: cùng bài toán, ba hợp đồng

Giả sử luồng chứa chuỗi `"ant"`, `"bear"`, `"cat"`. Ta muốn dùng ký tự đầu tiên làm khóa và độ dài chuỗi làm giá trị:

~~~java
s -> s.substring(0, 1)  // keyMapper: String -> String
String::length          // valueMapper: String -> Integer
~~~

Đây là các **biểu thức hàm minh họa**, chỉ dùng khi đặt trong `collect(...)` hoặc ngữ cảnh có functional interface thích hợp.

Ba câu lệnh có dạng:

~~~java
Map<String, Integer> ordinary = words.stream()
        .collect(Collectors.toMap(
                s -> s.substring(0, 1), String::length));

Map<String, Integer> immutable = words.stream()
        .collect(Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1), String::length));

ConcurrentMap<String, Integer> concurrent = words.parallelStream()
        .collect(Collectors.toConcurrentMap(
                s -> s.substring(0, 1), String::length));
~~~

*Đoạn này giả sử `words` có kiểu `List<String>`, các import phù hợp và các key không trùng.*

Về dữ liệu cuối cùng, cả ba đều có thể cho ánh xạ `a=3, b=4, c=3`. Nhưng:

- **`toUnmodifiableMap`**: trả `Map<K,V>` **không cho phép sửa các ánh xạ** sau khi thu thập.
- **`toMap`**: trả `Map<K,V>`; đặc tả **không cam kết** lớp triển khai cụ thể, mutability, tính tuần tự hóa hoặc thread-safety. Nếu **cần bảo đảm** một loại map mutable, hãy dùng overload có `mapFactory`.
- **`toConcurrentMap`**: trả `ConcurrentMap<K,V>` bằng một collector có đặc tính **`CONCURRENT`** và **`UNORDERED`**. Nó phù hợp khi tích lũy song song không cần giữ encounter order; **không nên nhầm** điều đó với cam kết kết quả luôn là một implementation cụ thể hoặc luôn cho phép mọi thao tác sửa.

Đặc biệt, **“trả một `Map`” không đồng nghĩa “map đó chắc chắn sửa được”**, và **“thu thập từ parallel stream” không đồng nghĩa “bắt buộc dùng `toConcurrentMap`”**.

## 2. Bảng so sánh tổng quan

| Thuộc tính | `toMap` | `toConcurrentMap` | `toUnmodifiableMap` |
| --- | --- | --- | --- |
| Kiểu kết quả | `Map<K,V>` | `ConcurrentMap<K,V>` | `Map<K,V>` |
| Collector `CONCURRENT` | **Không** | **Có** | **Không** |
| Collector `UNORDERED` | Không được đánh dấu `UNORDERED` ở các overload minh họa | **Có** | Không phải collector concurrent; không lấy thứ tự Map làm hợp đồng |
| Kết quả bảo đảm unmodifiable? | **Không có bảo đảm** | **Không có bảo đảm mutability** | **Có** |
| Có overload tự chọn `mapFactory`? | **Có** (4 tham số) | **Có** (4 tham số, supplier tạo `ConcurrentMap`) | **Không** |
| Hai tham số gặp khóa trùng | `IllegalStateException` | `IllegalStateException` | `IllegalStateException` |
| Có overload `mergeFunction`? | Có | Có | Có |
| Chạy được trên `parallelStream()`? | Có | Có | Có |
| Khả năng tối ưu khi gom song song không cần thứ tự | Phải gộp các map trung gian | Collector concurrent/unordered có thể hữu ích | Trả kết quả không sửa được; không phải concurrent collector |
| `null` từ key/value mapper | Phụ thuộc hợp đồng/implementation; không dựa vào việc nhận null, `toMap` hai tham số trên JDK kiểm thử ném NPE với null value | Các implementation mặc định phổ biến không chấp nhận null key/value; ví dụ kiểm thử ném NPE | **Từ chối rõ ràng cả null key và null value bằng NPE** |
| Thứ tự duyệt `Map` trả về | Không có bảo đảm lớp/iteration order nếu không chọn factory | Không dựa vào encounter order | Không có bảo đảm thứ tự duyệt |

**Đọc bảng đúng cách:** `CONCURRENT` là đặc tính của **collector**, không phải nhãn thay thế cho độ an toàn luồng của mọi object chứa trong map. `UNORDERED` là đặc tính thu thập, không hứa map sẽ tự sắp xếp khóa. Với `toConcurrentMap`, dù kiểu kết quả là `ConcurrentMap`, API vẫn không bảo đảm tên class cụ thể hay mutability; nếu muốn một `ConcurrentHashMap` mutable chắc chắn, cần chọn factory tường minh.

## 3. Các overload cần biết

### `Collectors.toMap`

~~~java
toMap(keyMapper, valueMapper)
toMap(keyMapper, valueMapper, mergeFunction)
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

- **Hai tham số:** mỗi key phải xuất hiện nhiều nhất một lần theo `equals`; nếu không, `collect` ném `IllegalStateException`.
- **Ba tham số:** khi key trùng, kết hợp hai value bằng `BinaryOperator<U> mergeFunction`.
- **Bốn tham số:** chọn map implementation qua `Supplier<M> mapFactory`. Ví dụ `LinkedHashMap::new` nếu cần map mutable có thứ tự chèn, hoặc `TreeMap::new` nếu cần khóa được sắp theo comparator tự nhiên/phù hợp.

`toMap` không phải concurrent collector, nhưng vẫn **được dùng với parallel stream**: stream framework kết hợp các map trung gian. Điều đó có thể tốn chi phí merge nhiều entry; không có nghĩa song song với `toMap` là sai hay không an toàn khi sử dụng đúng Stream API.

### `Collectors.toConcurrentMap`

~~~java
toConcurrentMap(keyMapper, valueMapper)
toConcurrentMap(keyMapper, valueMapper, mergeFunction)
toConcurrentMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

Nhóm này trả về `ConcurrentMap` và là collector `CONCURRENT`/`UNORDERED`. Overload bốn tham số yêu cầu factory tạo một `ConcurrentMap`, chẳng hạn `ConcurrentHashMap::new` hoặc `ConcurrentSkipListMap::new` với kiểu khóa phù hợp.

Nó không bảo đảm stream tự chạy nhanh hơn. Hiệu năng phụ thuộc lượng dữ liệu, phân bố key, độ tranh chấp khi nhiều phần tử tạo cùng khóa, chi phí tính toán và môi trường. Hãy đo trên workload thật nếu hiệu năng là mục tiêu.

### `Collectors.toUnmodifiableMap` — xuất hiện từ Java 10

~~~java
toUnmodifiableMap(keyMapper, valueMapper)
toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
~~~

Chỉ có **hai** overload này trong nhóm API đang xét. Không có overload nhận `mapFactory`, và kết quả được cam kết là **unmodifiable `Map`**. Nếu cần cấu trúc sắp xếp hay implementation cụ thể rồi muốn cung cấp read-only view, cần thiết kế riêng cách tạo/công bố dữ liệu; `toUnmodifiableMap` không cho chọn class đầu ra.

Phương thức này **không bỏ qua null**: theo Java API, nếu `keyMapper` hoặc `valueMapper` trả `null`, quá trình thu thập ném `NullPointerException`. Đó là điều kiện cần xử lý trước khi gọi collector.

## 4. Ví dụ hoàn chỉnh 1 — Cùng đầu vào, ba kết quả và hai factory tường minh

Lưu thành **`CollectorComparisonDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class CollectorComparisonDemo {
    static String key(String text) {
        return text.substring(0, 1);
    }

    public static void main(String[] args) {
        List<String> words = List.of("ant", "bear", "cat");

        Map<String, Integer> standard = words.stream()
                .collect(Collectors.toMap(
                        CollectorComparisonDemo::key, String::length));

        Map<String, Integer> immutable = words.stream()
                .collect(Collectors.toUnmodifiableMap(
                        CollectorComparisonDemo::key, String::length));

        ConcurrentMap<String, Integer> concurrent = words.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        CollectorComparisonDemo::key, String::length));

        System.out.println("toMap=" + new TreeMap<>(standard));
        System.out.println("unmodifiable=" + new TreeMap<>(immutable));
        System.out.println("concurrent=" + new TreeMap<>(concurrent));

        try {
            immutable.put("d", 5);
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable-put=UnsupportedOperationException");
        }

        LinkedHashMap<String, Integer> chosen = words.stream()
                .collect(Collectors.toMap(
                        CollectorComparisonDemo::key,
                        String::length,
                        (left, right) -> right,
                        LinkedHashMap::new));
        chosen.put("d", 5);
        System.out.println("chosen=" + chosen);

        ConcurrentHashMap<String, Integer> chosenConcurrent = words.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        CollectorComparisonDemo::key,
                        String::length,
                        Integer::sum,
                        ConcurrentHashMap::new));
        chosenConcurrent.put("d", 5);
        System.out.println("chosen-concurrent=" + new TreeMap<>(chosenConcurrent));
    }
}
~~~

Biên dịch và chạy trên một JDK còn hỗ trợ mục tiêu Java 10:

~~~bash
javac --release 10 CollectorComparisonDemo.java
java CollectorComparisonDemo
~~~

**Stdout chính xác:**

~~~text
toMap={a=3, b=4, c=3}
unmodifiable={a=3, b=4, c=3}
concurrent={a=3, b=4, c=3}
unmodifiable-put=UnsupportedOperationException
chosen={a=3, b=4, c=3, d=5}
chosen-concurrent={a=3, b=4, c=3, d=5}
~~~

Giải thích:

1. Ba dòng đầu có cùng các ánh xạ nhờ `keyMapper` và `valueMapper` giống nhau. Chúng dùng `new TreeMap<>(...)` chỉ **để in theo thứ tự ổn định**, không khẳng định các map nguồn được sắp xếp.
2. `immutable.put("d", 5)` ném `UnsupportedOperationException` đúng với hợp đồng `toUnmodifiableMap`.
3. `chosen` dùng supplier `LinkedHashMap::new`. Vì là class mutable được chỉ định rõ, thao tác `put` hợp lệ; trên stream tuần tự và không có duplicate, thứ tự chèn thể hiện theo thứ tự các từ nguồn.
4. `chosenConcurrent` dùng supplier `ConcurrentHashMap::new`. Đây là lựa chọn rõ ràng khi người viết **cần chính xác một concurrent map mutable**; `put` thành công.
5. `standard` từ overload hai tham số `toMap` **không được kiểm thử khả năng sửa** vì hợp đồng không bảo đảm mọi phiên bản/implementation trả map mutable. Nếu cần chắc chắn, hãy dùng factory như `chosen`.

Không nên kết luận rằng `toConcurrentMap` sẽ nhanh hơn chỉ từ ví dụ nhỏ này. Đây là minh họa *contract* và kiểu kết quả, không phải benchmark.

## 5. Khóa trùng — mặc định ném lỗi, có merge thì kết hợp

**Duplicate key** là khi hai phần tử đầu vào được `keyMapper` chuyển thành hai khóa được coi bằng nhau theo `equals`, không phải chỉ khi input object trùng hoàn toàn.

Với `"ant"` và `"apple"`, cả hai tạo khóa `"a"`. Nếu dùng overload hai tham số:

~~~java
words.stream().collect(Collectors.toMap(keyMapper, valueMapper));
words.stream().collect(Collectors.toUnmodifiableMap(keyMapper, valueMapper));
words.stream().collect(Collectors.toConcurrentMap(keyMapper, valueMapper));
~~~

*Ba dòng là minh họa cú pháp trong method, với `words`, `keyMapper` và `valueMapper` giả định.* Cả ba đều **ném `IllegalStateException`** khi gặp khóa trùng.

Đừng nhầm ngoại lệ này với `IllegalArgumentException` của `Map.of(...)` khi truyền literal key trùng. Trong Collector API đang xét, **`IllegalStateException`** là ngoại lệ của overload hai tham số gặp duplicate.

### Dùng `mergeFunction` cho duplicate

~~~java
Map<String, Integer> totals = words.stream()
        .collect(Collectors.toMap(
                s -> s.substring(0, 1), String::length, Integer::sum));
~~~

Khi hai value cùng khóa `"a"` là `3` và `5`, `Integer::sum` cho `8`. Có thể dùng merge function tương tự với `toConcurrentMap` và `toUnmodifiableMap`.

**Chú ý thiết kế merge:**

- Để thuận lợi khi thu thập song song, merge nên mang tính **kết hợp** (*associative*) và, khi thứ tự không được bảo đảm (đặc biệt với concurrent/unordered collector), nên mang tính **giao hoán** (*commutative*) nếu kết quả phải độc lập thứ tự.
- `Integer::sum` là ví dụ dễ kiểm chứng: cộng các số nguyên nhỏ trong phạm vi không tràn cho cùng kết quả bất kể thứ tự nhóm.
- Các merge function như `(oldValue, newValue) -> oldValue` hoặc phép nối chuỗi theo thứ tự có thể **phụ thuộc thứ tự xử lý**; với `toConcurrentMap` trên parallel stream, không nên dựa vào việc giá trị “đầu tiên” theo encounter order sẽ thắng.
- Một merge function theo `Map.merge` trả `null` có thể dẫn tới việc mapping bị xóa; đó không phải phương thức chung để giữ một giá trị nullable. Hãy thiết kế chính sách duplicate minh bạch.
- Các mapper và merge function cần tuân theo quy tắc non-interference của Stream API; đừng sửa nguồn hoặc state dùng chung một cách thiếu đồng bộ.

### Ví dụ hoàn chỉnh 2 — Ném lỗi và xử lý trùng bằng `Integer::sum`

Lưu **`DuplicateKeysDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class DuplicateKeysDemo {
    static String key(String text) {
        return text.substring(0, 1);
    }

    static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=accepted");
        } catch (IllegalStateException expected) {
            System.out.println(label + "=IllegalStateException");
        }
    }

    public static void main(String[] args) {
        List<String> words = List.of("ant", "apple", "bee");

        check("toMap-duplicate", () -> words.stream()
                .collect(Collectors.toMap(DuplicateKeysDemo::key, String::length)));

        check("toUnmodifiableMap-duplicate", () -> words.stream()
                .collect(Collectors.toUnmodifiableMap(DuplicateKeysDemo::key, String::length)));

        check("toConcurrentMap-duplicate", () -> words.stream()
                .collect(Collectors.toConcurrentMap(DuplicateKeysDemo::key, String::length)));

        Map<String, Integer> standard = words.stream()
                .collect(Collectors.toMap(
                        DuplicateKeysDemo::key, String::length, Integer::sum));

        Map<String, Integer> immutable = words.stream()
                .collect(Collectors.toUnmodifiableMap(
                        DuplicateKeysDemo::key, String::length, Integer::sum));

        ConcurrentMap<String, Integer> concurrent = words.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        DuplicateKeysDemo::key, String::length, Integer::sum));

        System.out.println("toMap-sum=" + new TreeMap<>(standard));
        System.out.println("unmodifiable-sum=" + new TreeMap<>(immutable));
        System.out.println("concurrent-sum=" + new TreeMap<>(concurrent));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 DuplicateKeysDemo.java
java DuplicateKeysDemo
~~~

Stdout:

~~~text
toMap-duplicate=IllegalStateException
toUnmodifiableMap-duplicate=IllegalStateException
toConcurrentMap-duplicate=IllegalStateException
toMap-sum={a=8, b=3}
unmodifiable-sum={a=8, b=3}
concurrent-sum={a=8, b=3}
~~~

Ba kết quả cuối cùng bằng nhau về **dữ liệu**, không đồng nghĩa các collector giống nhau về thread-safety, mutability hoặc quy tắc thứ tự.

## 6. So sánh quy tắc null

**`toUnmodifiableMap` có bảo đảm mạnh nhất trong ba nhóm về null**: không được tạo khóa `null` và không được tạo giá trị `null`. Nếu một mapper trả null, `collect` ném `NullPointerException`. Hãy chuẩn hóa đầu vào trước khi thu thập.

Với `toMap` và `toConcurrentMap`, cần thận trọng hơn về phát biểu:

- `toMap` hai tham số của JDK được kiểm thử ném NPE khi `valueMapper` trả null. Không nên dựa vào việc **null key** chắc chắn được nhận: API không cam kết implementation map cụ thể; `HashMap` và `TreeMap` có chính sách null khác nhau. Khi tự chọn `mapFactory`, phải tuân theo hợp đồng của class đó.
- `toConcurrentMap` với collector mặc định của JDK được kiểm thử ném NPE nếu key hoặc value mapper trả null. Các concurrent map phổ biến như `ConcurrentHashMap` cũng không nhận null key/value. Ngay cả với custom factory, không nên dùng null làm tín hiệu thiếu dữ liệu trong một pipeline concurrent.
- Với `toUnmodifiableMap`, **cả null key và null value bị cấm theo hợp đồng Javadoc**, không phụ thuộc vào sự tình cờ của một implementation.

Nếu một mapper có thể trả null, chọn một trong ba cách:

1. **Loại bỏ** bản ghi không có dữ liệu bắt buộc bằng `filter` trước `collect`, hoặc lọc sau bước `map` có khả năng sinh null.
2. **Thay bằng giá trị domain hợp lệ**, chẳng hạn một key mặc định khác null, nếu quy tắc nghiệp vụ cho phép.
3. **Báo lỗi rõ ràng** bằng `Objects.requireNonNull(value, "message")` hoặc kiểm tra dữ liệu đầu vào trước pipeline, thay vì để collector báo lỗi chung.

Đừng âm thầm lọc mất một bản ghi bắt buộc nếu null biểu thị lỗi dữ liệu.

### Ví dụ hoàn chỉnh 3 — Null key/value và một pipeline được làm sạch

Lưu **`NullAndMappingDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NullAndMappingDemo {
    static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=accepted");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        check("unmodifiable-null-key", () -> Stream.of("a", "bad")
                .collect(Collectors.toUnmodifiableMap(
                        s -> "bad".equals(s) ? null : s, String::length)));

        check("unmodifiable-null-value", () -> Stream.of("a", "bad")
                .collect(Collectors.toUnmodifiableMap(
                        s -> s, s -> "bad".equals(s) ? null : s.length())));

        check("concurrent-null-key", () -> Stream.of("a", "bad")
                .collect(Collectors.toConcurrentMap(
                        s -> "bad".equals(s) ? null : s, String::length)));

        check("concurrent-null-value", () -> Stream.of("a", "bad")
                .collect(Collectors.toConcurrentMap(
                        s -> s, s -> "bad".equals(s) ? null : s.length())));

        check("toMap-null-value", () -> Stream.of("a", "bad")
                .collect(Collectors.toMap(
                        s -> s, s -> "bad".equals(s) ? null : s.length())));

        Map<String, Integer> cleaned = Stream.of("a", null, "bb")
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableMap(s -> s, String::length));
        System.out.println("cleaned=" + new TreeMap<>(cleaned));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 NullAndMappingDemo.java
java NullAndMappingDemo
~~~

**Stdout chính xác:**

~~~text
unmodifiable-null-key=NullPointerException
unmodifiable-null-value=NullPointerException
concurrent-null-key=NullPointerException
concurrent-null-value=NullPointerException
toMap-null-value=NullPointerException
cleaned={a=1, bb=2}
~~~

Những trường hợp kiểm tra lỗi cho thấy hành vi của JDK chạy ví dụ. Quy tắc **được tài liệu API cam kết trực tiếp** trong nhóm này là `toUnmodifiableMap` không nhận null key/value. `cleaned` cho thấy việc lọc null ở nguồn trước khi gọi `String::length` và collector.

**Lưu ý vị trí lỗi:** Nếu `valueMapper` là `String::length` và input chính nó là null, lời gọi mapper có thể ném NPE trước khi collector xử lý giá trị. Vì vậy, khi chẩn đoán stack trace, cần tìm **bước nào thực sự truy cập null**, không mặc định NPE luôn đến từ factory map.

## 7. Collector concurrent khác với parallel stream như thế nào?

`parallelStream()` yêu cầu Stream API cho phép xử lý pipeline song song khi thích hợp. Nhưng đặc tính **`CONCURRENT`** là lời hứa của **collector** về cách tích lũy vào vùng kết quả; hai khái niệm không giống nhau.

- `toMap` có thể nhận dữ liệu từ parallel stream, nhưng bản thân collector **không mang `CONCURRENT`**. Framework tích lũy kết quả trung gian rồi dùng *combiner* ghép các map.
- `toConcurrentMap` mang `CONCURRENT` và `UNORDERED`, nên trong điều kiện thích hợp có thể tích lũy đồng thời vào concurrent result container. Nó không yêu cầu key đã sắp xếp và không cam kết thứ tự encounter.
- `toUnmodifiableMap` vẫn có thể dùng trên parallel stream; thành phẩm không sửa được. **Không biến nó thành concurrent collector** chỉ vì stream xử lý song song, cũng không tự làm các object value mutable an toàn luồng.

### Ví dụ hoàn chỉnh 4 — Cùng kết quả đếm, khác đặc tính collector

Lưu **`ParallelMapCollectorsDemo.java`**:

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelMapCollectorsDemo {
    public static void main(String[] args) {
        Collector<Integer, ?, Map<Integer, Integer>> ordinaryCollector =
                Collectors.toMap(n -> n % 4, n -> 1, Integer::sum);

        Collector<Integer, ?, ConcurrentMap<Integer, Integer>> concurrentCollector =
                Collectors.toConcurrentMap(n -> n % 4, n -> 1, Integer::sum);

        Collector<Integer, ?, Map<Integer, Integer>> immutableCollector =
                Collectors.toUnmodifiableMap(n -> n % 4, n -> 1, Integer::sum);

        Map<Integer, Integer> ordinary = IntStream.rangeClosed(1, 1000)
                .parallel().boxed().collect(ordinaryCollector);

        ConcurrentMap<Integer, Integer> concurrent = IntStream.rangeClosed(1, 1000)
                .parallel().boxed().collect(concurrentCollector);

        Map<Integer, Integer> immutable = IntStream.rangeClosed(1, 1000)
                .parallel().boxed().collect(immutableCollector);

        System.out.println("ordinary=" + new TreeMap<>(ordinary));
        System.out.println("concurrent=" + new TreeMap<>(concurrent));
        System.out.println("unmodifiable=" + new TreeMap<>(immutable));

        System.out.println("toMap-CONCURRENT=" + ordinaryCollector.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));

        System.out.println("toConcurrentMap-CONCURRENT=" + concurrentCollector.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));

        System.out.println("toConcurrentMap-UNORDERED=" + concurrentCollector.characteristics()
                .contains(Collector.Characteristics.UNORDERED));

        System.out.println("toUnmodifiableMap-CONCURRENT=" + immutableCollector.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ParallelMapCollectorsDemo.java
java ParallelMapCollectorsDemo
~~~

Stdout:

~~~text
ordinary={0=250, 1=250, 2=250, 3=250}
concurrent={0=250, 1=250, 2=250, 3=250}
unmodifiable={0=250, 1=250, 2=250, 3=250}
toMap-CONCURRENT=false
toConcurrentMap-CONCURRENT=true
toConcurrentMap-UNORDERED=true
toUnmodifiableMap-CONCURRENT=false
~~~

`IntStream.rangeClosed(1, 1000)` có 1.000 số, mỗi phần dư khi chia 4 xuất hiện 250 lần. Vì `Integer::sum` có kết quả không phụ thuộc thứ tự gộp trong phạm vi này, ba collector cho cùng map. Tuy nhiên chỉ `toConcurrentMap` có hai đặc tính collector cần lưu ý ở trên.

**Không suy ra lợi thế hiệu năng từ stdout.** Để chọn giữa `toMap` và `toConcurrentMap` cho tập lớn, nên đo benchmark có phương pháp: số phần tử, số key khác nhau, độ tranh chấp khi cùng key, chi phí mapper/merge, lượng luồng, cấu hình JVM và GC đều ảnh hưởng.

## 8. Lựa chọn thứ tự, kiểu Map cụ thể và khả năng sửa

### Nếu cần Map mutable theo một class nhất định

Dùng overload bốn tham số của `toMap`:

~~~java
LinkedHashMap<String, Integer> ordered = words.stream()
        .collect(Collectors.toMap(
                s -> s.substring(0, 1),
                String::length,
                (left, right) -> right,
                LinkedHashMap::new));
~~~

Đây là **đoạn minh họa trong method**, giả sử `words` chứa chuỗi và import phù hợp. Với stream tuần tự có encounter order, `LinkedHashMap` duy trì thứ tự chèn. Tuy nhiên policy `(left, right) -> right` là **chọn value phía phải** khi key trùng; hãy bảo đảm policy này khớp nghiệp vụ, thay vì chọn chỉ để thỏa chữ ký phương thức.

Nếu muốn một map có khóa sắp xếp, chọn `TreeMap::new` với kiểu key/comparator phù hợp. Nếu cần truy cập đồng thời và chỉ rõ class, dùng overload bốn tham số của `toConcurrentMap` với `ConcurrentHashMap::new` hoặc implementation `ConcurrentMap` thích hợp.

### Nếu cần một Map không sửa đổi

Khi các mapper non-null và không yêu cầu loại implementation cụ thể:

~~~java
Map<String, Integer> result = words.stream()
        .collect(Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                String::length,
                Integer::sum));
~~~

`result` không thể bị sửa bằng `put` hoặc `remove`; đây là điểm khác biệt **được bảo đảm** so với hai nhóm collector còn lại. Tuy nhiên nếu value là `List` hoặc domain object mutable, `toUnmodifiableMap` không tự sao chép sâu những object ấy.

Nếu đã có một map mutable được tạo trước đó, `Map.copyOf(mutableMap)` cũng có thể tạo một kết quả không sửa đổi từ các ánh xạ hiện có. Đây là lựa chọn cho **snapshot từ một map**, khác với `toUnmodifiableMap` thu thập **trực tiếp từ Stream**. Cả hai đều không tự đóng băng sâu giá trị mutable.

### Nếu cần map vừa sắp xếp vừa không cho caller sửa

`toUnmodifiableMap` không nhận map factory, nên không hứa iteration order. Một lựa chọn thiết kế riêng là tạo `TreeMap`, xây dữ liệu xong và chỉ trả `Collections.unmodifiableSortedMap(...)` qua API, đồng thời **không tiết lộ/thay đổi backing map**. Wrapper này là view, không phải tự động deep snapshot; nếu backing map vẫn có người khác sửa thì nội dung quan sát có thể thay đổi. Lựa chọn nào phù hợp tùy yêu cầu thứ tự, quyền sở hữu dữ liệu và concurrent access.

## 9. Thread-safety, immutability và các giới hạn cần nhớ

### `ConcurrentMap` không làm key/value tự an toàn luồng

`toConcurrentMap` cho một container có hợp đồng truy cập đồng thời của `ConcurrentMap`. Nhưng nếu value là `ArrayList` hoặc một object có setter không được đồng bộ, việc lấy value rồi sửa nó vẫn có thể phát sinh data race. Map concurrent **không tự biến các đối tượng trong map thành thread-safe**.

Khi tổng hợp giá trị từ parallel stream, nên dùng merge function không có side effect không được đồng bộ, và không mutate một list dùng chung ngoài các quy tắc concurrency được thiết kế rõ ràng.

### `Unmodifiable` không nhất thiết là immutable sâu

`toUnmodifiableMap` chặn thay đổi **các cặp ánh xạ ở tầng map**, nhưng nếu một value được giữ dưới dạng reference đến object mutable, state bên trong value vẫn có thể thay đổi. Muốn snapshot sâu hơn, hãy sao chép/chuyển đổi từng value (và key nếu cần) sang cấu trúc immutable phù hợp **trước khi hoàn thiện** map.

### `parallelStream()` không bảo đảm nhanh

Với tập nhỏ hoặc mapper rẻ, chi phí chia việc và ghép kết quả có thể lớn hơn lợi ích. `toConcurrentMap` có thể hữu ích khi nhiều phần tử độc lập và không cần duy trì encounter order, nhưng key collision cao có thể tạo tranh chấp. Quyết định dựa vào profile/benchmark chứ không phải tên collector.

### Không thay đổi source khi Stream đang chạy

Tránh thay đổi collection nguồn từ pipeline `map`/`merge` hoặc từ một thread khác nếu không có giao thức đồng bộ/chế độ nguồn phù hợp. Collector concurrent không tự làm cho việc thay đổi nguồn tùy ý trở nên an toàn.

## 10. Quy trình chọn collector theo yêu cầu

| Nhu cầu | Khuyến nghị ban đầu | Điều cần kiểm tra |
| --- | --- | --- |
| Tạo lookup map chỉ đọc để công bố qua API | `toUnmodifiableMap` | Mapper không trả null; duplicate đã được xử lý; value có immutable không |
| Gom thành một map theo key từ stream thông thường | `toMap` | Có duplicate không? Có cần factory để bảo đảm mutability/iteration order không |
| Cần cụ thể một `HashMap`/`LinkedHashMap` mutable | `toMap(..., merge, factory)` | Merge policy phù hợp và supplier đúng class |
| Cần một kết quả có interface `ConcurrentMap` và collector concurrent/unordered | `toConcurrentMap` | Không cần encounter order; merge an toàn khi song song |
| Cần cụ thể `ConcurrentHashMap` mutable | `toConcurrentMap(..., merge, ConcurrentHashMap::new)` | Key/value hợp lệ; không dựa vào thứ tự duyệt |
| Key có thể trùng, muốn cộng số lượng | Cả ba nhóm với `Integer::sum` | Kiểm tra overflow khi lượng dữ liệu lớn; merge phải phù hợp |
| Key có thể trùng, muốn “bản ghi mới nhất” theo một trường thời gian | Merge dựa trên timestamp/priority rõ ràng | Không dùng thứ tự thread để quyết định “mới nhất” |
| Mapper có thể trả null | Validate/filter/đổi cách mô hình trước `collect` | `toUnmodifiableMap` từ chối null; đừng dựa vào hành vi tình cờ của map implementation |
| Cần Map có thứ tự khóa ổn định | Chọn `TreeMap` qua `toMap` factory, hoặc chiến lược riêng | `toUnmodifiableMap`/`toConcurrentMap` mặc định không hứa thứ tự |
| Chỉ có map sẵn và muốn snapshot unmodifiable | `Map.copyOf(existingMap)` | Vẫn là sao chép nông của key/value; nguồn đang bị sửa đồng thời cần quản lý riêng |

**Checklist ngắn:** xác định (1) key có thể trùng không; (2) chính sách merge; (3) có null không; (4) cần sửa map sau đó không; (5) cần concurrent aggregation không; (6) có yêu cầu thứ tự không; (7) key/value có mutable không. Trả lời các câu này trước sẽ giúp tránh chọn collector bằng cảm tính.

## 11. Lỗi phổ biến và hướng sửa

**Lỗi 1 — “`toMap` mặc định luôn trả `HashMap` mutable.”** Không được Javadoc bảo đảm. Nếu code cần map mutable cụ thể, dùng overload có supplier.

**Lỗi 2 — “`toConcurrentMap` không thể dùng với stream tuần tự.”** Sai. Collector này vẫn có thể được sử dụng với `stream()`; đặc tính concurrent/unordered chỉ cho biết cách collector có thể được dùng, không bắt buộc nguồn là parallel.

**Lỗi 3 — “`toMap` không được dùng với `parallelStream()`.”** Sai. Nó có thể được dùng song song; framework kết hợp các map trung gian. Khác biệt với `toConcurrentMap` là cách tích lũy và đặc tính collector, không phải một lệnh cấm.

**Lỗi 4 — “`toUnmodifiableMap` có overload `mapFactory`.”** Không có. Nếu cần loại map hoặc ordering cụ thể, thiết kế việc tạo/công bố map theo cách khác.

**Lỗi 5 — “Có key trùng thì collector sẽ tự ghi đè giá trị cũ.”** Với overload hai tham số của cả ba nhóm, key trùng ném `IllegalStateException`. Muốn ghi đè hay kết hợp, phải cung cấp merge function thích hợp.

**Lỗi 6 — “Lấy `(a,b)->a` với parallel/concurrent sẽ luôn giữ phần tử đầu tiên của Stream.”** Không nên kỳ vọng điều này với `toConcurrentMap` là unordered collector. Nếu cần bản ghi theo tiêu chí nghiệp vụ, so sánh timestamp/sequence ID rõ ràng và định nghĩa quy tắc hòa.

**Lỗi 7 — “`toUnmodifiableMap` bỏ qua null hoặc tạo entry có null.”** Sai; mapper trả null key/value dẫn đến `NullPointerException`. Nếu null là hợp lệ trong domain, cần mô hình hóa hoặc xử lý trước.

**Lỗi 8 — “Map unmodifiable có nghĩa value immutable.”** Sai; value mutable vẫn có thể bị thay đổi qua reference khác. Cần freeze hoặc copy các tầng cần thiết.

**Lỗi 9 — “Map concurrent bảo đảm mọi phép sửa object value an toàn luồng.”** Không. Chỉ container tuân theo hợp đồng concurrent map; state bên trong value do chương trình chịu trách nhiệm.

**Lỗi 10 — “In trực tiếp Map rồi so sánh thứ tự là unit test đáng tin cậy.”** Không với map không có thứ tự được cam kết. So sánh `Map.equals` hoặc `size`/`get`; nếu phải in theo thứ tự, dùng `new TreeMap<>(result)` khi key hỗ trợ sắp xếp.

## 12. Câu hỏi tự kiểm tra

1. Cả ba collector nhận `keyMapper` và `valueMapper`. Khác biệt rõ nhất về mutability giữa `toUnmodifiableMap` và `toMap` là gì?
2. `toMap` có thể dùng trên parallel stream không? Nó có phải concurrent collector không?
3. `toConcurrentMap` có hai đặc tính collector nào quan trọng?
4. Dùng overload hai tham số và xuất hiện hai phần tử có key bằng nhau thì ba collector xử lý thế nào?
5. Vì sao `Integer::sum` phù hợp với bài toán đếm/gộp kết quả song song?
6. Nếu key là `null` từ mapper, `toUnmodifiableMap` làm gì? Có nên dựa vào việc một implementation của `toMap` đôi khi nhận null key không?
7. Khi cần chính xác `LinkedHashMap` mutable, dùng overload nào?
8. Nếu dùng `toUnmodifiableMap` tạo `Map<String, List<String>>`, một list value mutable có tự trở thành không sửa được không?
9. Vì sao `toConcurrentMap` trên parallel stream không bảo đảm lúc nào cũng chạy nhanh hơn `toMap`?
10. Muốn có một map unmodifiable từ map đã tồn tại, có thể dùng API nào khác với việc thu thập Stream?

**Đáp án:**

1. `toUnmodifiableMap` **bảo đảm** kết quả không sửa được; `toMap` không bảo đảm mutability của loại map trả về.
2. Có thể; nhưng `toMap` không phải collector `CONCURRENT`.
3. `CONCURRENT` và `UNORDERED`.
4. Cả ba ném `IllegalStateException` khi duplicate key mà không có merge function.
5. Phép cộng (khi không tràn) kết hợp và giao hoán; kết quả không phụ thuộc thứ tự gộp.
6. `NullPointerException`; không, hãy xử lý null rõ ràng.
7. `Collectors.toMap(keyMapper, valueMapper, mergeFunction, LinkedHashMap::new)`.
8. Không; map ngoài unmodifiable nhưng list bên trong vẫn là cùng reference, cần xử lý riêng.
9. Chi phí, mức độ tranh chấp, số lượng key, merge và môi trường thực thi có thể khác nhau; cần đo.
10. `Map.copyOf(existingMap)`, nhớ rằng key/value object vẫn được sao chép nông.

## 13. Tham khảo tài liệu Java vẫn còn áp dụng

- **Oracle Javadoc — `Collectors` (Java SE 26), chứa các overload `toMap`, `toConcurrentMap`, `toUnmodifiableMap`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- **Oracle Javadoc — `Collector.Characteristics`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html
- **Oracle Javadoc — `ConcurrentMap`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentMap.html
- **Oracle Javadoc — `Map` và `Map.copyOf`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html
- **Oracle Core Libraries Guide — Creating Unmodifiable Lists, Sets, and Maps:** https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html

**Kết luận:** Chọn `toUnmodifiableMap` nếu **cần một kết quả map không sửa được** và dữ liệu đã hợp lệ; chọn `toMap` khi cần gom map thông thường hoặc chỉ định concrete implementation; chọn `toConcurrentMap` khi cần **collector concurrent/unordered** với `ConcurrentMap`. Với cả ba, hãy giải quyết **key trùng**, **null**, **hàm merge**, **thứ tự** và **tính mutable của key/value** dựa trên hợp đồng API thực tế, không dựa vào class mặc định tình cờ của JDK.