# Ảnh hưởng của kết quả hợp nhất đến nội dung `Map` khi dùng Collector

*Chủ đề: Java 10 — Collector bản đồ. Bài học tập trung vào `Collectors.toMap`, `Collectors.toUnmodifiableMap`, hàm `mergeFunction` và quy tắc `Map.merge` vẫn được áp dụng trên Java 17+ và những bản Java hiện đại. Các ví dụ dùng Java 17 để có thể biên dịch, chạy và kiểm chứng kết quả.*

## 1. Vấn đề thực tế: nhiều phần tử đầu vào cùng một khóa

Một `Map<K,V>` chỉ lưu **một ánh xạ cho mỗi khóa**. Nhưng khi chuyển một tập dữ liệu thành Map bằng Stream, có thể có nhiều bản ghi tạo ra cùng một khóa.

Giả sử hệ thống có năm dòng bán hàng:

~~~text
Mã hàng   Số lượng
A        2
B        3
A        5
B        1
C        4
~~~

Nếu key là mã hàng, hai dòng `A` va chạm vào cùng một khóa; hai dòng `B` cũng vậy. Kết quả phải là gì?

- **Cộng số lượng:** `A=7, B=4, C=4`.
- **Giữ dòng đầu:** `A=2, B=3, C=4`.
- **Giữ dòng cuối:** `A=5, B=1, C=4`.
- **Lấy số lượng lớn nhất:** `A=5, B=3, C=4`.
- **Loại khóa nếu gặp xung đột:** khóa bị xóa khi hàm hợp nhất trả `null`; lần xuất hiện kế tiếp có thể tạo ánh xạ mới.
- **Giữ mọi dòng:** dùng `groupingBy` để tạo `Map<K,List<V>>`, thay vì ép nhiều giá trị thành một `V`.

**Đây chính là ảnh hưởng của kết quả hợp nhất đến nội dung Map:** một `mergeFunction` không chỉ quyết định **giá trị cuối cùng**, mà còn có thể khiến một **khóa biến mất**, được thêm lại, hoặc làm kết quả phụ thuộc vào thứ tự kết hợp.

## 2. Hai dạng `Collectors.toMap` và vai trò của `mergeFunction`

### 2.1. Không chỉ định hàm hợp nhất

~~~java
var sales = List.of(
    new Sale("A", 2),
    new Sale("A", 5)
);

// Phát sinh IllegalStateException khi collect vì khóa A trùng:
var result = sales.stream()
    .collect(Collectors.toMap(Sale::sku, Sale::quantity));
~~~

Đây là đoạn minh họa trong lớp có `record Sale(String sku, int quantity)`, `List` và `Collectors`; tệp hoàn chỉnh ở mục 7. Dạng hai đối số:

~~~java
Collectors.toMap(keyMapper, valueMapper)
~~~

phù hợp khi **mỗi phần tử tạo một khóa duy nhất**. Khi hai phần tử tạo khóa bằng nhau theo `equals`, collector ném `IllegalStateException`. **Kể cả hai giá trị bằng nhau**, xung đột khóa vẫn bị coi là lỗi. Không được mong collector tự giữ bản ghi đầu hoặc cuối.

### 2.2. Có hàm hợp nhất

~~~java
var totals = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku,
        Sale::quantity,
        Integer::sum
    ));
~~~

Dạng ba đối số:

~~~java
Collectors.toMap(keyMapper, valueMapper, mergeFunction)
~~~

có ba vai trò:

1. `keyMapper` xác định khóa `K` của phần tử đầu vào (ví dụ `Sale::sku`).
2. `valueMapper` xác định giá trị `V` (ví dụ `Sale::quantity` trả `int` được boxing thành `Integer`).
3. `mergeFunction` nhận **hai giá trị có cùng khóa** để tính **giá trị sẽ lưu thay thế**.

Với `Integer::sum`, dữ liệu `A=2` và `A=5` hợp nhất thành `A=7`. Từ đó nếu một dòng `A=4` khác xuất hiện, phép hợp nhất tiếp theo có thể cộng `7+4=11`.

Dạng bốn đối số cho phép chọn implementation của Map:

~~~java
var totals = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku,
        Sale::quantity,
        Integer::sum,
        LinkedHashMap::new
    ));
~~~

`LinkedHashMap::new` giúp tạo Map có thứ tự duyệt theo quy tắc của `LinkedHashMap`. Nó không thay đổi chính sách xử lý khóa trùng: giá trị vẫn do `Integer::sum` quyết định.

### 2.3. Kiểu của hàm hợp nhất

Dạng tổng quát:

~~~java
BinaryOperator<V> mergeFunction
~~~

Nó nhận hai giá trị cùng loại `V` và trả một giá trị `V`, hoặc **có thể trả `null`** nếu muốn ánh xạ bị xóa theo `Map.merge`. Ví dụ:

~~~java
(oldValue, newValue) -> oldValue + newValue
(oldValue, newValue) -> oldValue
(oldValue, newValue) -> newValue
(oldValue, newValue) -> Math.max(oldValue, newValue)
~~~

**Đừng nhầm:** hàm hợp nhất nhận **giá trị cũ và giá trị mới**, không phải hai đối tượng `Sale` nguồn, trừ khi `valueMapper` trả chính các đối tượng đó. Nó cũng không tự nhận khóa `K`. Nếu cần xử lý phụ thuộc trực tiếp vào khóa, hãy thiết kế dữ liệu/giá trị hoặc bước xử lý khác có thông tin khóa.

## 3. Cơ chế: `Map.merge` chi phối việc giá trị nào còn lại

Javadoc của `Collectors.toMap(keyMapper,valueMapper,mergeFunction)` nêu rõ hàm hợp nhất được dùng như trong `Map.merge(key, value, remappingFunction)`. Hiểu API này giúp dự đoán kết quả.

Với một Map mutable, quy tắc đơn giản:

- **Khóa chưa có ánh xạ tới giá trị khác null:** chèn giá trị mới (phải khác null) mà **không cần gọi** hàm hợp nhất.
- **Khóa đã ánh xạ tới giá trị khác null:** gọi hàm với `oldValue` và `newValue`.
- **Hàm trả một giá trị khác null:** thay ánh xạ cũ bằng giá trị đó.
- **Hàm trả `null`:** **xóa ánh xạ của khóa**; không lưu `key -> null`.
- **Phần tử cùng khóa đến sau khi bị xóa:** có thể được thêm lại như khóa mới.

Mô phỏng:

~~~java
Map<String, Integer> map = new HashMap<>();

map.merge("A", 2, Integer::sum); // A chưa có: A -> 2
map.merge("A", 5, Integer::sum); // A đã có: A -> 7
map.merge("A", 1, (oldValue, newValue) -> null);
// Xóa khóa A; map.containsKey("A") == false
~~~

Đoạn ví dụ này dùng API `Map.merge` trực tiếp. `Collectors.toMap` dùng cùng nguyên tắc để xử lý khóa trùng. Nó **không** hoạt động như một biểu thức `put(key, null)`.

### Bảng trạng thái trước/sau hợp nhất

| Map trước | Bản ghi mới | Kết quả hàm hợp nhất | Map sau |
| --- | --- | --- | --- |
| `{}` | `A -> 2` | Không gọi hàm | `{A=2}` |
| `{A=2}` | `A -> 5` | `2 + 5 = 7` | `{A=7}` |
| `{A=7}` | `A -> 1` | `null` | `{}` |
| `{}` | `A -> 4` | Không gọi hàm | `{A=4}` |
| `{A=4}` | `B -> 3` | Không gọi hàm | `{A=4,B=3}` |

**Lưu ý:** các ví dụ trong bảng là cách lý giải tuần tự để hiểu hành vi. Trong pipeline song song, collector có thể tạo nhiều Map trung gian rồi gộp chúng; hàm merge có thể được gọi khi kết hợp các Map đó. Không dựa vào số lần gọi và thứ tự thời gian của callback merge để tạo logic nghiệp vụ có tác dụng phụ.

## 4. Các chính sách hợp nhất và nội dung kết quả

Giả sử:

~~~java
var sales = List.of(
    new Sale("A", 2),
    new Sale("B", 3),
    new Sale("A", 5),
    new Sale("B", 1),
    new Sale("C", 4)
);
~~~

### 4.1. Cộng dồn số lượng

~~~java
var totals = sales.stream().collect(
    Collectors.toMap(Sale::sku, Sale::quantity, Integer::sum));
~~~

Kết quả ánh xạ:

~~~text
A -> 7
B -> 4
C -> 4
~~~

Hợp lý cho tổng số lượng, tổng số lượt, tổng điểm khi các giá trị có thể cộng. Với số nguyên trong nghiệp vụ có nguy cơ tràn `int`, cân nhắc `long` hoặc `Math.addExact`/kiểu số phù hợp; không coi `Integer::sum` là cơ chế tự phát hiện overflow.

### 4.2. Giữ giá trị đầu

~~~java
var first = sales.stream().collect(
    Collectors.toMap(
        Sale::sku, Sale::quantity,
        (oldValue, newValue) -> oldValue));
~~~

Kết quả ở stream tuần tự có thứ tự của ví dụ:

~~~text
A -> 2
B -> 3
C -> 4
~~~

Cách này phù hợp **chỉ khi** nghiệp vụ muốn lấy giá trị xuất hiện đầu tiên theo một thứ tự xác định. Cần chỉ rõ thứ tự nguồn: ví dụ dữ liệu đã được sắp theo thời điểm hoặc số thứ tự ưu tiên. Nếu nguồn là `HashSet`, map không có encounter order đáng dựa vào để diễn giải “đầu tiên”.

### 4.3. Giữ giá trị sau

~~~java
var last = sales.stream().collect(
    Collectors.toMap(
        Sale::sku, Sale::quantity,
        (oldValue, newValue) -> newValue));
~~~

Kết quả theo thứ tự List đầu vào:

~~~text
A -> 5
B -> 1
C -> 4
~~~

Đây là chính sách thường gặp cho “bản ghi sau ghi đè bản ghi trước”. Nhưng “sau” phải được xác định theo dữ liệu: nếu danh sách không có thứ tự thời gian, dùng cách này chỉ vì gọi là `last` có thể dẫn đến sai logic.

Với dữ liệu nhiều bản cập nhật, thường tốt hơn là chọn giá trị có **timestamp/sequence lớn nhất** theo một comparator rõ ràng, thay vì phụ thuộc vào thứ tự các bản ghi đến luồng xử lý.

### 4.4. Chọn giá trị lớn nhất

~~~java
var max = sales.stream().collect(
    Collectors.toMap(Sale::sku, Sale::quantity, Integer::max));
~~~

Kết quả:

~~~text
A -> 5
B -> 3
C -> 4
~~~

`Integer::max` phù hợp khi muốn lấy mức lớn nhất. Với các object có nhiều trường, dùng hàm so sánh tiêu chí rõ ràng (và nếu cần, tie-breaker) để chọn kết quả có tính quyết định.

### 4.5. Ghép chuỗi

Với dữ liệu chuỗi:

~~~java
var contacts = List.of(
    Map.entry("Lan", "111"),
    Map.entry("Lan", "222"),
    Map.entry("Mai", "333")
);

var phones = contacts.stream().collect(
    Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue,
        (a, b) -> a + ", " + b
    ));
~~~

Map có khóa `"Lan"` và giá trị `"111, 222"` trong stream tuần tự đã có thứ tự của ví dụ. Ghép chuỗi **không giao hoán**; đảo thứ tự dữ liệu có thể đổi kết quả. Nếu mục tiêu là lưu **danh sách nhiều số liên hệ** thay vì một chuỗi khó phân tích, hãy cân nhắc `groupingBy` với downstream `mapping`.

### 4.6. Bỏ ánh xạ khi hợp nhất trả `null`

~~~java
var removed = List.of(
    new Sale("A", 1),
    new Sale("A", 2)
).stream().collect(Collectors.toMap(
    Sale::sku, Sale::quantity,
    (oldValue, newValue) -> null
));

// removed.containsKey("A") == false
~~~

Sau `A=1`, dòng thứ hai `A=2` gây xung đột và hàm trả `null`: khóa `A` bị **xóa**. Bây giờ xét:

~~~java
var reinserted = List.of(
    new Sale("A", 1),
    new Sale("A", 2),
    new Sale("B", 3),
    new Sale("A", 4)
).stream().collect(Collectors.toMap(
    Sale::sku, Sale::quantity,
    (oldValue, newValue) -> null
));

// Map cuối cùng chứa A=4 và B=3.
~~~

Giải thích: `A=1` được thêm; `A=2` loại bỏ `A`; `B=3` được thêm; `A=4` được thêm lại, vì ở thời điểm ấy `A` không còn trong map. Vì vậy, **hàm trả null không có nghĩa “cấm khóa này mãi mãi”**.

Chính sách “mỗi lần trùng là xóa” rất dễ gây bất ngờ, nhất là với dữ liệu có nhiều lần lặp, khi chạy song song hoặc kết hợp nhiều Map trung gian. Nếu nghiệp vụ thực sự muốn “loại tất cả khóa từng có trùng”, hãy **đếm hoặc nhóm các giá trị trước**, rồi lọc những nhóm có số bản ghi lớn hơn một. Đó là chính sách khác với `(a,b) -> null`.

## 5. Dữ liệu trùng nhau và chính sách xung đột

Nhiều lập trình viên nghĩ rằng collector không có `mergeFunction` sẽ chỉ báo lỗi khi **giá trị** khác nhau. Thực tế, sự va chạm được quyết định bởi **khóa**:

~~~java
var events = List.of("A", "A");

// Vẫn lỗi vì cả hai tạo cùng key "A", dù giá trị cũng "A":
var map = events.stream().collect(
    Collectors.toMap(s -> s, s -> s));
~~~

Đây là một đoạn minh họa **cố ý gây `IllegalStateException`**, không nên chạy nối tiếp mà không bắt ngoại lệ.

Khi muốn chấp nhận các bản ghi trùng nội dung, có thể chọn:

~~~java
var map = events.stream().collect(
    Collectors.toMap(
        s -> s,
        s -> s,
        (existing, incoming) -> existing));
~~~

Tuy nhiên, quy tắc “chấp nhận trùng giống nhau nhưng **từ chối trùng có nội dung khác**” cần được thể hiện rõ:

~~~java
var map = records.stream().collect(
    Collectors.toMap(
        Record::key,
        Record::value,
        (left, right) -> {
            if (!Objects.equals(left, right)) {
                throw new IllegalArgumentException("Conflicting values for one key");
            }
            return left;
        }
    ));
~~~

Đây là **pseudocode theo ngữ cảnh**: cần có lớp dữ liệu `Record` với `key()` và `value()`, import `Objects` và xử lý lỗi chi tiết phù hợp. Thông điệp quan trọng là không bỏ qua xung đột dữ liệu chỉ vì collector có thể kỹ thuật cho phép lấy một giá trị bất kỳ.

**Khóa được xem là trùng theo quan hệ bằng nhau của `K`**, thường liên quan `equals` và `hashCode` trong hash map; không phải do chuỗi hiển thị giống nhau về mặt ngôn ngữ. Cân nhắc chuẩn hóa mã khóa (`strip`/case normalization theo nghiệp vụ) **trước** khi đưa vào collector, nếu cần.

## 6. `null` trong `valueMapper` khác `null` từ `mergeFunction`

Hai trường hợp cần phân biệt nghiêm ngặt:

| `null` xuất phát từ đâu? | Hậu quả cần hiểu |
| --- | --- |
| `valueMapper` tạo ra `null` rồi truyền làm giá trị để `Map.merge` | Không hợp lệ: `Map.merge` yêu cầu giá trị mới **khác null**; `Collectors.toMap` dạng có merge có thể ném `NullPointerException` |
| `mergeFunction` trả `null` trong lúc có khóa xung đột | **Xóa ánh xạ** của khóa, không lưu value null |
| `keyMapper` cho ra `null` | Không nên dựa vào việc được chấp nhận; phụ thuộc map implementation và API collector; phải thiết kế chính sách key null |
| `Collectors.toUnmodifiableMap` với key/value null | **Từ chối** null key/value theo hợp đồng của collector |
| `Map.merge(key, null, function)` trực tiếp | Ném `NullPointerException` vì giá trị mới bắt buộc không-null |

Ví dụ lỗi khi mapper tạo giá trị null:

~~~java
// Pseudocode minh họa lỗi runtime với mapper giá trị:
var result = Stream.of("A").collect(Collectors.toMap(
    key -> key,
    key -> (Integer) null,
    Integer::sum
));
// NullPointerException, không tạo Map chứa A -> null.
~~~

Khi null là một giá trị nghiệp vụ hợp lệ, `toMap` với `Map.merge` không phải cơ chế tự lưu null theo ý muốn. Cần xác định policy: loại bản ghi, từ chối, mô hình hóa trạng thái thiếu (`Optional`/kiểu kết quả riêng) hoặc dùng quy trình map phù hợp và kiểm soát null rõ ràng.

`Collectors.toUnmodifiableMap` từ Java 10 còn có ràng buộc **không thể sửa kết quả**, không nhận null ở key/value. **Không suy diễn** rằng vì merger có thể trả null nên map cuối sẽ có entry với value null. Ở ngữ nghĩa merge, null chỉ làm mất entry.

## 7. Chương trình Java 17+ hoàn chỉnh, đã kiểm thử

Chương trình này tạo nhiều Map từ cùng một danh sách bán hàng và **in các Map qua `TreeMap`** để thứ tự khóa trong stdout cố định. Nó còn so sánh `Map.merge` trực tiếp, minh họa merge null xóa/khóa được thêm lại, phát hiện khóa trùng không có merger, tạo map unmodifiable và kiểm tra trường hợp song song.

~~~java
// File: MapCollectorMergeDemo.java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapCollectorMergeDemo {
    record Sale(String sku, int quantity) { }

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("A", 2), new Sale("B", 3),
                new Sale("A", 5), new Sale("B", 1),
                new Sale("C", 4));

        var totals = sales.stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity, Integer::sum));
        var first = sales.stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity,
                        (oldValue, newValue) -> oldValue));
        var last = sales.stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity,
                        (oldValue, newValue) -> newValue));
        var max = sales.stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity, Integer::max));
        var ordered = sales.stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity,
                        Integer::sum, LinkedHashMap::new));

        System.out.println("sum = " + new TreeMap<>(totals));
        System.out.println("first = " + new TreeMap<>(first));
        System.out.println("last = " + new TreeMap<>(last));
        System.out.println("max = " + new TreeMap<>(max));
        System.out.println("linked order = " + ordered);

        var removed = List.of(new Sale("A", 1), new Sale("A", 2))
                .stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity,
                        (oldValue, newValue) -> null));
        System.out.println("null merge removes A = " + !removed.containsKey("A"));

        var reinserted = List.of(new Sale("A", 1), new Sale("A", 2),
                        new Sale("B", 3), new Sale("A", 4))
                .stream()
                .collect(Collectors.toMap(Sale::sku, Sale::quantity,
                        (oldValue, newValue) -> null));
        System.out.println("after new A arrives = " + new TreeMap<>(reinserted));

        try {
            sales.stream().collect(Collectors.toMap(Sale::sku, Sale::quantity));
            System.out.println("duplicate without merge = accepted");
        } catch (IllegalStateException expected) {
            System.out.println("duplicate without merge = rejected");
        }

        var unmodifiable = sales.stream().collect(
                Collectors.toUnmodifiableMap(Sale::sku, Sale::quantity, Integer::sum));
        try {
            unmodifiable.put("A", 99);
            System.out.println("unmodifiable mutation = accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable mutation = blocked");
        }

        var parallelTotals = sales.parallelStream().collect(
                Collectors.toMap(Sale::sku, Sale::quantity, Integer::sum));
        System.out.println("parallel sum matches = " + totals.equals(parallelTotals));

        var groups = sales.stream().collect(
                Collectors.groupingBy(Sale::sku,
                        Collectors.mapping(Sale::quantity, Collectors.toList())));
        System.out.println("grouped = " + new TreeMap<>(groups));

        Map<String, Integer> manual = new LinkedHashMap<>();
        manual.merge("A", 2, Integer::sum);
        manual.merge("A", 5, Integer::sum);
        System.out.println("Map.merge A = " + manual.get("A"));
        manual.merge("A", 1, (oldValue, newValue) -> null);
        System.out.println("Map.merge removed A = " + !manual.containsKey("A"));
    }
}
~~~

Lưu đúng tệp `MapCollectorMergeDemo.java` và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 MapCollectorMergeDemo.java
java MapCollectorMergeDemo
~~~

Stdout đã kiểm chứng:

~~~text
sum = {A=7, B=4, C=4}
first = {A=2, B=3, C=4}
last = {A=5, B=1, C=4}
max = {A=5, B=3, C=4}
linked order = {A=7, B=4, C=4}
null merge removes A = true
after new A arrives = {A=4, B=3}
duplicate without merge = rejected
unmodifiable mutation = blocked
parallel sum matches = true
grouped = {A=[2, 5], B=[3, 1], C=[4]}
Map.merge A = 7
Map.merge removed A = true
~~~

**Giải thích đầu ra:**

1. `totals` cộng các số lượng cùng mã; `first` giữ bản ghi đầu trong nguồn có thứ tự; `last` giữ bản ghi sau; `max` chọn giá trị lớn nhất. Bốn chính sách cho **Map khác nhau trên cùng dữ liệu**.
2. `ordered` dùng `LinkedHashMap` để duy trì thứ tự duyệt khóa theo thứ tự chèn trong pipeline tuần tự: `A`, `B`, `C`. Tham số `mapFactory` không thay đổi phép cộng.
3. Hàm `(oldValue,newValue)->null` làm xóa `A` sau hai dòng đầu. Nếu một dòng `A` khác đến sau đó, key có thể được thêm lại.
4. Dạng `toMap` không có mergeFunction **từ chối khóa trùng** bằng `IllegalStateException`; chương trình bắt lỗi thay vì để kết thúc.
5. `Collectors.toUnmodifiableMap` trả map không thể sửa; thử `put` phát sinh `UnsupportedOperationException`.
6. `parallelTotals` bằng `totals` với `Integer::sum` và dữ liệu trong ví dụ. Kết luận này phản ánh một hàm hợp nhất thích hợp cho phép cộng, không phải bảo đảm cho mọi hàm có side effect hoặc phụ thuộc thứ tự.
7. `grouped` dùng `groupingBy` giữ **hai giá trị riêng** của mã A trong `List<Integer>` thay vì gộp thành một số; hai phương pháp biểu diễn dữ liệu khác nhau.
8. `Map.merge` trực tiếp cho `A=7` rồi xóa `A` khi remapping function trả null, minh họa nguồn gốc quy tắc của collector.

## 8. Hợp nhất trong stream song song: điều kiện để nội dung Map ổn định

`Collectors.toMap` dạng có merge **không phải concurrent collector**. Khi pipeline song song, runtime có thể:

1. Chia các phần tử thành nhiều nhóm để xử lý.
2. Tạo các Map trung gian trong các tác vụ khác nhau.
3. Dùng bước *combiner* hợp nhất các Map trung gian, gọi hàm merge ở những khóa trùng.

Do đó, hàm merger không được phụ thuộc vào việc “luôn được gọi từ trái sang phải theo từng bản ghi trong một vòng for” khi sử dụng song song.

### 8.1. Associativity là yêu cầu nền tảng

Với các giá trị `a,b,c`, phép toán **kết hợp** (*associative*) thỏa:

~~~text
merge(merge(a, b), c) == merge(a, merge(b, c))
~~~

Nếu không kết hợp, cách chia nhóm có thể làm kết quả khác nhau. Một số lựa chọn thường tốt cho dữ liệu phù hợp:

- `Integer::sum` để tính tổng số nguyên theo chính sách số phù hợp.
- `Integer::max` hoặc `Integer::min` để chọn lớn nhất/nhỏ nhất.
- Phép hợp nhất tạo cấu trúc mới và giữ đúng thứ tự nếu hợp đồng collector yêu cầu, nhưng phải kiểm tra kỹ chi phí.

Ví dụ **không kết hợp**:

~~~java
(oldValue, newValue) -> oldValue - newValue
~~~

Vì `(10-3)-2 = 5` nhưng `10-(3-2) = 9`. Với parallel stream, không dùng phép trừ này làm merger nếu bạn mong nhận cùng một kết quả độc lập cách chia nhóm.

### 8.2. Commutativity và thứ tự

Phép giao hoán (*commutative*) thỏa `merge(a,b)==merge(b,a)`. Nó khác với tính kết hợp. `Integer::sum` vừa kết hợp vừa giao hoán trong ngữ nghĩa số nguyên Java, nên không phụ thuộc thứ tự các giá trị khi tính tổng (nhưng vẫn có thể tràn `int`).

Ngược lại:

~~~java
(oldValue, newValue) -> oldValue  // Giữ giá trị phía trái
(oldValue, newValue) -> newValue  // Giữ giá trị phía phải
~~~

hai phép này **có tính kết hợp** nhưng **không giao hoán**. Với ordered stream và non-concurrent collector tôn trọng encounter order, chúng có ý nghĩa theo thứ tự của nguồn; nhưng với **unordered stream**, `toConcurrentMap` hoặc nguồn không cam kết thứ tự, không nên gắn ý nghĩa nghiệp vụ “bản ghi đầu/cuối” vào chúng.

Nếu cần chọn bản ghi mới nhất theo thời gian **bất kể thứ tự xử lý**, hãy viết merger so sánh timestamp/sequence và có tie-breaker thích hợp. “Giá trị được xử lý sau” không nhất thiết là “giá trị có thời gian nghiệp vụ mới nhất”.

### 8.3. Tránh side effect và mutate Map trong merger

~~~java
// Không nên dùng một bộ đếm chia sẻ để quyết định kết quả:
(oldValue, newValue) -> {
    globalCounter++;
    return globalCounter % 2 == 0 ? oldValue : newValue;
}
~~~

Đây là pseudocode minh họa **cách thiết kế sai**, không phải đoạn mã độc lập. Merge function nên gần với một hàm thuần (*pure*): với cùng hai đầu vào, trả cùng đầu ra, không sửa state ngoài, không ghi trực tiếp vào chính Map đang được collect, không làm I/O, không phụ thuộc giờ hiện tại hoặc thứ tự scheduler.

Đặc biệt với dữ liệu số thực `double`, cộng dồn có thể khác một chút do **sai số dấu phẩy động và thứ tự nhóm**: phép cộng floating-point không hoàn toàn kết hợp. Với dữ liệu tài chính cần chính xác theo đơn vị, cân nhắc kiểu `BigDecimal` và quy tắc làm tròn rõ ràng thay vì kỳ vọng kết quả `double` bất biến với mọi cách thực thi.

### 8.4. `toConcurrentMap` có hợp đồng khác

`Collectors.toConcurrentMap` tạo kết quả `ConcurrentMap` và được thiết kế cho việc collect concurrent; nó phù hợp khi không cần bảo toàn encounter order. Tuy nhiên, việc dùng collection concurrent **không tự làm merger phụ thuộc thứ tự trở nên xác định**.

Khi logic cần “dòng sau trong file” ghi đè “dòng trước”, nên xem xét xử lý tuần tự theo nguồn ordered, hoặc chọn bản ghi theo tiêu chí thời gian/sequence trong mỗi value để kết quả không phụ thuộc thứ tự thực thi. Đừng thay `toMap` bằng `toConcurrentMap` chỉ để tăng tốc mà bỏ qua ngữ nghĩa của merger.

## 9. `mergeFunction` quyết định giá trị, `mapFactory` quyết định cấu trúc

Hai vai trò phải tách biệt:

- `mergeFunction`: khi trùng key, **value mới là gì** (hoặc xóa mapping nếu trả null)?
- `mapFactory`: dùng **loại Map nào** để giữ và duyệt kết quả?

Ví dụ, nếu cần các khóa in ra theo thứ tự chèn từ danh sách nguồn có thứ tự:

~~~java
var ordered = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Sale::quantity,
        Integer::sum,
        LinkedHashMap::new
    ));
~~~

Trong pipeline tuần tự, `LinkedHashMap` giữ thứ tự chèn khóa `A`, `B`, `C`. Nhưng **không** dựa vào thứ tự duyệt của Map mặc định do `Collectors.toMap` trả về: API không cam kết implementation của nó.

Khi cần thứ tự **theo khóa**, có thể dùng:

~~~java
var sortedByKey = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Sale::quantity,
        Integer::sum,
        TreeMap::new
    ));
~~~

`TreeMap` sắp theo thứ tự tự nhiên của `String` trong ví dụ. Nếu khóa không có thứ tự tự nhiên phù hợp, cần comparator tương thích; dùng `TreeMap` cũng có ràng buộc riêng về khả năng so sánh key.

**Thứ tự không thay thế chính sách merge.** Kết quả có thể in theo `A,B,C`, nhưng tổng `A=7` hay giá trị cuối `A=5` vẫn do merger lựa chọn.

## 10. Muốn giữ tất cả giá trị của mỗi khóa thì dùng `groupingBy`

Không phải bài toán nào cũng nên giảm nhiều bản ghi về một value. Nếu cần lưu cả các bản ghi có cùng mã:

~~~java
var bySku = sales.stream().collect(
    Collectors.groupingBy(
        Sale::sku,
        Collectors.mapping(Sale::quantity, Collectors.toList())
    )
);
~~~

Kiểu kết quả về mặt logic:

~~~java
Map<String, List<Integer>>
~~~

Với dữ liệu mẫu:

~~~text
A -> [2, 5]
B -> [3, 1]
C -> [4]
~~~

`groupingBy` phù hợp nếu muốn **mọi giá trị** của mỗi nhóm để phân tích, kiểm tra bất thường hoặc tính nhiều thống kê sau đó. Ngược lại, `toMap(..., Integer::sum)` là lựa chọn rõ ràng khi chỉ muốn tổng.

Đôi khi người ta cố tạo `Map<K,List<V>>` bằng `toMap`:

~~~java
var grouped = sales.stream().collect(
    Collectors.toMap(
        Sale::sku,
        sale -> List.of(sale.quantity()),
        (left, right) -> Stream.concat(left.stream(), right.stream()).toList()
    )
);
~~~

Về ý tưởng, đoạn code trên có thể gom danh sách theo key. Tuy nhiên, việc nối và tạo danh sách mới ở **mỗi lần va chạm** có thể tốn chi phí với nhóm lớn. Nếu chỉ muốn nhóm tất cả bản ghi theo khóa, `groupingBy(..., mapping(..., toList()))` thường là lựa chọn có ý định rõ hơn và tránh tự thiết kế merger phức tạp.

Không tự mutate đối tượng `List` hay map dùng chung từ nhiều nơi trong merger khi chưa kiểm soát aliasing, thread-safety và hợp đồng Collector.

## 11. `toUnmodifiableMap` và `Map.copyOf` sau hợp nhất

### 11.1. Nếu cần Map không thể sửa từ Collector

Java 10 có:

~~~java
var readOnly = sales.stream().collect(
    Collectors.toUnmodifiableMap(
        Sale::sku,
        Sale::quantity,
        Integer::sum
    )
);
~~~

`readOnly` là `Map<String,Integer>` không thể sửa: thao tác `put`, `remove` hay thay đổi qua view không được hỗ trợ. Collector này vẫn sử dụng merger để xử lý khóa trùng, nhưng có ràng buộc **không chấp nhận null key/value** trong kết quả mapping.

`Collectors.toUnmodifiableMap(keyMapper,valueMapper)` **không có merger** sẽ ném `IllegalStateException` khi khóa trùng, giống dạng hai đối số của `toMap`.

Nếu cần nhập dữ liệu mutable trước, rồi xuất bản:

~~~java
var totals = sales.stream().collect(
    Collectors.toMap(Sale::sku, Sale::quantity, Integer::sum));
var published = Map.copyOf(totals);
~~~

`Map.copyOf` tạo một map không thể sửa, không phản ánh thay đổi cấu trúc/value sau đó của `totals`. Nó từ chối null key/value. Nếu `totals` đã unmodifiable phù hợp, API có thể tái sử dụng nguồn; đừng dựa vào `==` hoặc kỳ vọng mỗi lần `copyOf` đều cấp phát object mới.

### 11.2. Không dựa vào iteration order của unmodifiable Map factory

Dù mã đầu vào có thứ tự, kết quả `toUnmodifiableMap`/`Map.copyOf` không cam kết thứ tự duyệt khóa cố định. Nếu cần format output ổn định, hãy dùng `new TreeMap<>(map)` hoặc một cấu trúc hiển thị có thứ tự rõ. Nếu cần giữ thứ tự insertion-order để công khai, lựa chọn Map structure và cách bọc phải có chủ đích; đừng gán yêu cầu ấy cho `Map.copyOf`.

### 11.3. Bất biến nông và value object

“Unmodifiable Map” ngăn thay đổi entry/key-value mappings thông qua Map, nhưng nếu một value là một `List` mutable hoặc object mutable, trạng thái của đối tượng bên trong vẫn có thể thay đổi. Muốn xuất bản dữ liệu nhất quán, nên tạo các value bất biến hoặc snapshot phù hợp **trước** khi copy map.

## 12. Khi hàm hợp nhất ném ngoại lệ hoặc trả giá trị không hợp lệ

Có các chính sách hợp lệ cho xung đột:

~~~java
(oldValue, newValue) -> {
    if (!Objects.equals(oldValue, newValue)) {
        throw new IllegalArgumentException("Conflicting values");
    }
    return oldValue;
}
~~~

Trong collector, nếu merger ném unchecked exception, thao tác `collect` sẽ thất bại; không nhận được Map kết quả thành công. Đừng giả định Map đã hoàn thành một phần là trạng thái có thể sử dụng khi collect thất bại. Nếu ứng dụng cần báo tất cả xung đột thay vì dừng tại xung đột đầu tiên, cần một bước kiểm tra hoặc nhóm dữ liệu có hệ thống.

Với hàm hợp nhất trả **một đối tượng mutable**, không được thay đổi trạng thái phá vỡ các bất biến của nghiệp vụ hoặc dùng kết quả để cache bất biến nếu value không được copy. Merger nên có hợp đồng rõ về việc nó trả object nào, có sở hữu value đó hay không và có tồn tại tham chiếu đến nó ở nơi khác không.

Nếu merger trả `null` do lỗi tính toán ngoài dự kiến (ví dụ phương thức lookup trả null), Map có thể âm thầm **mất khóa** thay vì có giá trị null. Đây là lỗi nguy hiểm. Khi null **không có nghĩa xóa khóa**, có thể kiểm tra:

~~~java
(oldValue, newValue) -> Objects.requireNonNull(
        chooseValue(oldValue, newValue), "merged value"
)
~~~

Đây là pseudocode khi `chooseValue` được định nghĩa trong lớp. Nó biến một giá trị null bất ngờ thành lỗi được phát hiện, không cho merger vô tình xóa khóa.

Nếu muốn loại tất cả khóa có xung đột khỏi kết quả cuối, **không** nên dùng `(a,b)->null` vì khóa có thể quay trở lại khi bản ghi cùng key xuất hiện lần ba. Hãy dùng `groupingBy` để đếm trước, rồi chọn những key có số lần xuất hiện bằng một.

## 13. Bài tập và đáp án

### Bài 1. Dạng không có merger

~~~java
var input = List.of("A", "B", "A");
var result = input.stream().collect(
    Collectors.toMap(s -> s, String::length)
);
~~~

**Hỏi:** Kết quả là gì?

**Đáp án:** `IllegalStateException` khi xử lý khóa `A` trùng. Hai giá trị cùng là `1` cũng không khiến xung đột tự biến mất.

### Bài 2. Cộng dồn

~~~java
var result = List.of(2, 5, 3).stream().collect(
    Collectors.toMap(n -> "A", n -> n, Integer::sum)
);
~~~

**Đáp án:** Map có một entry `A=10`.

### Bài 3. Giữ đầu hay giữ cuối

~~~java
var input = List.of(
    Map.entry("A", "old"),
    Map.entry("A", "new")
);
~~~

Nếu dùng `toMap(Map.Entry::getKey,Map.Entry::getValue,(x,y)->x)` thì `A=old`; nếu dùng `(x,y)->y` thì `A=new` trong stream tuần tự có thứ tự của ví dụ.

### Bài 4. Hàm merge trả null

~~~java
var result = List.of(1, 2).stream().collect(
    Collectors.toMap(x -> "A", x -> x, (a, b) -> null)
);
~~~

**Đáp án:** Map kết quả không có khóa `A`. `null` từ merge làm **xóa mapping**, không có entry `A=null`.

### Bài 5. Trường hợp xuất hiện lần ba

~~~java
var result = List.of(1, 2, 3).stream().collect(
    Collectors.toMap(x -> "A", x -> x, (a, b) -> null)
);
~~~

**Đáp án:** Ở pipeline tuần tự, bản ghi thứ hai làm mất `A`, bản ghi thứ ba thêm lại, nên Map cuối có `A=3`. Đó là lý do không dùng hàm này để “cấm tất cả khóa bị trùng”.

### Bài 6. Chọn cấu trúc giữ tất cả bản ghi

Đầu vào có ba `Sale` cùng sku `A` với quantity `2, 5, 3`. Muốn output là `Map<String,List<Integer>>` chứa `A=[2,5,3]`, nên dùng gì?

**Đáp án:** `Collectors.groupingBy(Sale::sku, Collectors.mapping(Sale::quantity,Collectors.toList()))` trên stream có thứ tự là cách rõ hơn việc tự tạo merger nối list.

### Bài 7. Stream song song

Tại sao `(x,y)->x-y` không phù hợp khi muốn kết quả ổn định giữa các cách gộp?

**Đáp án:** Phép trừ **không kết hợp**: `(10-3)-2` khác `10-(3-2)`. Combiner trong parallel stream có thể nhóm khác đi. Hãy chọn phép kết hợp đúng với mô hình dữ liệu hoặc chuyển cách xử lý để bảo toàn trình tự nghiệp vụ.

### Bài 8. MapFactory

~~~java
var result = sales.stream().collect(
    Collectors.toMap(Sale::sku, Sale::quantity,
                     Integer::sum, LinkedHashMap::new));
~~~

**Đáp án:** `LinkedHashMap::new` chọn cấu trúc Map và hành vi duyệt theo insertion order; `Integer::sum` vẫn quyết định values khi trùng sku. Không nhầm mapFactory với mergeFunction.

### Bài 9. Không được sửa Map đã xuất bản

~~~java
var published = sales.stream().collect(
    Collectors.toUnmodifiableMap(
        Sale::sku, Sale::quantity, Integer::sum));
published.put("A", 999);
~~~

**Đáp án:** `put` ném `UnsupportedOperationException` vì Map từ `toUnmodifiableMap` không thể sửa.

### Bài 10. Phân biệt null

Tại sao `(oldVal,newVal)->null` có thể hợp lệ trong merger, nhưng `valueMapper` trả null lại gây lỗi?

**Đáp án:** `Map.merge` dùng null **trong kết quả remapping** để xóa ánh xạ. Ngược lại, tham số `value` mới được truyền vào `Map.merge` **phải khác null**. Hai vị trí dùng null có ngữ nghĩa khác nhau.

## 14. Checklist chọn chính sách merge đúng

- **Khóa có thực sự duy nhất không?** Nếu trùng là lỗi dữ liệu, dùng `toMap` hai đối số để từ chối hoặc validation cụ thể.
- **Nếu trùng, chọn giá trị nào?** Sum, max, first, last, latest theo timestamp, hay giữ tất cả?
- **Hàm merge có thể trả null không?** Nếu có, bạn có thật sự muốn **xóa mapping**? Đã kiểm thử trường hợp bản ghi thứ ba chưa?
- **Giá trị đầu vào có thể null không?** Chọn quy tắc kiểm tra trước khi collect; đừng nhầm null valueMapper với null merge result.
- **Chọn bản ghi đầu/cuối dựa vào thứ tự nào?** Nguồn có encounter order và có chính sách thời gian/sequence rõ không?
- **Có chạy song song không?** Hàm merger có tính kết hợp, ổn định, không side effect và phù hợp thứ tự không?
- **Có dùng `toConcurrentMap` không?** Kết quả có còn được diễn giải theo thứ tự hợp lệ của nghiệp vụ không?
- **Map cần giữ thứ tự duyệt không?** Chọn `LinkedHashMap` hoặc `TreeMap` ở mapFactory; không dựa vào Map mặc định.
- **Giữ một giá trị hay toàn bộ lịch sử?** Nếu cần nhiều values cho mỗi key, cân nhắc `groupingBy`.
- **Cần kết quả không thể sửa không?** `toUnmodifiableMap` hoặc `Map.copyOf` phù hợp, nhưng không cam kết bất biến sâu của value.
- **Tính đúng ở các ca biên:** Không dữ liệu, một khóa duy nhất, khóa trùng 2/3/n lần, giá trị null, merger trả null, xung đột chính sách, dữ liệu song song.
- **Đã kiểm thử stdout hoặc giá trị theo key chưa?** Không so sánh thứ tự in tùy ý của HashMap; dùng `get`/`equals` hoặc sắp theo key khi cần đầu ra ổn định.

## 15. Tài liệu chính thức còn hiệu lực

- [Java SE API — `Collectors.toMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toMap(java.util.function.Function,java.util.function.Function,java.util.function.BinaryOperator)): dạng có merger, va chạm khóa, combiner của parallel stream và giới hạn kết quả Map.
- [Java SE API — `Collectors.toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): collector Map không thể sửa từ Java 10, cách xử lý khóa trùng và null.
- [Java SE API — `Map.merge`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): xác định chính xác việc thêm, thay giá trị và xóa key khi merger trả null.
- [Java SE API — `Collectors.groupingBy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): lưu nhiều values theo key và downstream `mapping`.
- [Java SE API — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html): map duyệt theo insertion order hoặc access order theo cấu hình, phù hợp khi cần thứ tự rõ.
- [Java SE API — `TreeMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html): map sắp xếp theo khóa.
- [Java SE API — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): reduction, encounter order và xử lý song song.
- [JLS `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): `var` suy luận kiểu tĩnh của biến cục bộ từ biểu thức khởi tạo.

**Ghi nhớ:** Trong `Collectors.toMap`, **khóa trùng buộc phải có chính sách hợp nhất**, và kết quả của `mergeFunction` quyết định giá trị cuối cùng hoặc **xóa hoàn toàn mapping nếu trả null**. Sau khi xóa, key vẫn có thể được thêm lại bởi bản ghi kế tiếp. Hãy chọn merger phù hợp nghiệp vụ, kiểm soát tính kết hợp khi chạy song song, chọn Map implementation nếu cần thứ tự, và dùng `groupingBy` khi mục tiêu thật sự là giữ mọi giá trị của mỗi khóa.