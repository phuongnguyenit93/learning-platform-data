# Objects.isNull, Objects.nonNull và lọc dữ liệu trong Java

> **Module:** Java 8 — **Số học**. Bài giải thích `Objects.isNull` và `Objects.nonNull`, sử dụng với `Stream.filter`, xử lý danh sách số dạng wrapper có giá trị `null`, phân biệt **thiếu dữ liệu** với **số 0**, lọc an toàn trước khi unbox/cộng/trung bình, và tránh những lỗi khi lọc các record lồng nhau, grouping, sorting, `Optional` hoặc dữ liệu thực. Các API được trình bày thuộc Java 8 và **vẫn áp dụng trên Java hiện hành**.

## 1. Tư duy đúng: null là trạng thái thiếu tham chiếu, không phải con số

Hãy hình dung một danh sách kết quả đo số lượng:

~~~text
[null, 0, 12, null, -3, 5]
~~~

Ở đây:

- `null` là **không có đối tượng Integer tại vị trí đó**. Nghiệp vụ có thể hiểu là missing, chưa đo, dữ liệu không hợp lệ hoặc không áp dụng — nhưng Java không tự xác định nghĩa nào đúng.
- `0` là **một số nguyên hợp lệ**. Không thể tự coi bằng “chưa có dữ liệu”.
- `-3` là số âm hợp lệ; chỉ loại nếu nghiệp vụ không cho giá trị âm.
- `12`, `5` là số dương hợp lệ.
- Nếu dữ liệu có dạng `Double`, `NaN` và `Infinity` cũng là **giá trị double** chứ không phải `null`.

Cách tính tổng trên các số **đã có giá trị**:

~~~java
List<Integer> numbers =
        Arrays.asList(null, 0, 12, null, -3, 5);

long total = numbers.stream()
        .filter(Objects::nonNull)
        .mapToLong(Integer::longValue)
        .sum();

// total == 14.
~~~

Đây là **đoạn Java 8 minh họa**, cần import `java.util.Arrays`, `java.util.List` và `java.util.Objects`. Nó loại hai tham chiếu null, **giữ số 0 và số âm** rồi cộng 0+12-3+5=14.

Nhưng **bỏ các phần tử null là quyết định nghiệp vụ**, không phải quy tắc số học phổ quát. Nếu số liệu ảnh hưởng thanh toán, audit hoặc báo cáo chất lượng, việc lặng lẽ bỏ hai lần đo thiếu có thể gây hiểu lầm nghiêm trọng. Nên theo dõi số lượng giá trị thiếu và nêu rõ chính sách thống kê.

### 1.1. Ba câu hỏi phải trả lời trước khi lọc

1. **Null có được phép xuất hiện không?** Danh sách từ CSV, JSON, JDBC, map hoặc dịch vụ khác có thể chứa null.
2. **Null mang nghĩa gì?** Thiếu quan sát, lỗi dữ liệu, không áp dụng hay thực sự cần reject toàn bộ batch?
3. **Sau khi xử lý null, thống kê dùng mẫu nào?** Tổng có thể bằng nhau nhưng trung bình theo số phần tử hợp lệ khác trung bình coi missing là zero.

**Nguyên tắc:** `Objects.nonNull` là công cụ lọc tham chiếu; nó **không thay thế data contract**.

## 2. Định nghĩa chính xác theo Java 8 API

`java.util.Objects` là utility class chứa các static methods cho object references. Hai phương thức Java 8:

~~~java
public static boolean isNull(Object obj)
public static boolean nonNull(Object obj)
~~~

Hợp đồng:

| Giá trị đầu vào | `Objects.isNull` | `Objects.nonNull` |
| --- | --- | --- |
| `null` | `true` | `false` |
| `Integer.valueOf(0)` | `false` | `true` |
| `""` (chuỗi rỗng) | `false` | `true` |
| `"   "` (chuỗi chỉ khoảng trắng) | `false` | `true` |
| `Double.NaN` đóng hộp | `false` | `true` |
| `Collections.emptyList()` | `false` | `true` |
| Object đã được khởi tạo | `false` | `true` |

Ví dụ:

~~~java
System.out.println(Objects.isNull(null)); // true
System.out.println(Objects.nonNull(null)); // false
System.out.println(Objects.nonNull(0));    // true
~~~

Ở dòng cuối, `0` là primitive `int` và có thể được **autobox** thành Integer để truyền tới tham số Object; object đó không null. Đừng dùng `Objects.nonNull` để kiểm tra một số có khác zero hay không.

### 2.1. Tương đương với == null và != null

Về logic kiểm tra tham chiếu:

~~~java
Objects.isNull(value)   // tương đương value == null
Objects.nonNull(value)  // tương đương value != null
~~~

Cả hai cách đều hợp lệ. Trong câu lệnh `if`, cú pháp `value == null` thường là cách ngắn và rõ ràng:

~~~java
if (value == null) {
    return;
}
~~~

Trong `Stream.filter`, method reference có thể gọn hơn lambda:

~~~java
stream.filter(Objects::nonNull)
stream.filter(Objects::isNull)
~~~

Javadoc Java 8 thậm chí ghi chú chính hai method này được thiết kế để dùng dưới dạng **Predicate** cho `filter`.

### 2.2. Những gì chúng KHÔNG làm

`Objects.isNull/nonNull`:

- Không lấy giá trị mặc định.
- Không tạo mới object nếu null.
- Không gọi validation trên nội dung String hay object.
- Không kiểm tra số bằng 0 hay âm.
- Không kiểm tra `NaN`/`Infinity`.
- Không giải quyết null của các field nằm bên trong object khác.
- Không đảm bảo một object sẽ **mãi không null** nếu một reference được cập nhật đồng thời.
- Không kiểm tra dữ liệu business có hợp lệ không.

**Nullness check** chỉ trả một boolean dựa trên reference tại lúc đánh giá.

### 2.3. Khác với Objects.requireNonNull

~~~java
Objects.requireNonNull(value, "value is required");
~~~

`requireNonNull` kiểm tra object và **ném `NullPointerException` nếu null**. Nó phù hợp ở method boundary/constructor khi tham số bắt buộc phải có; ngược lại `nonNull` chỉ trả boolean và phù hợp với pipeline muốn bỏ qua phần tử vắng mặt.

### 2.4. Khác với Objects.equals

~~~java
Objects.equals(null, null);       // true
Objects.equals(null, "hello");    // false
Objects.equals("a", "a");         // true
~~~

`Objects.equals(a,b)` so sánh hai references null-safe theo equality contract; nó không thay cho việc lọc phần tử null. Đừng nhầm `Objects.isNull(x)` với `Objects.equals(x, null)` chỉ vì có thể cho cùng boolean trong một số trường hợp; `isNull` bộc lộ ý định trực tiếp hơn.

## 3. Vì sao Objects::nonNull phù hợp Stream.filter?

`Stream.filter` nhận một `Predicate<? super T>`, tức hàm kiểm tra mỗi phần tử có được giữ lại không. Còn `Objects.nonNull(Object)` trả boolean. Method reference `Objects::nonNull` tạo predicate có thể nhận phần tử kiểu T (nhờ Object là kiểu tổng quát).

~~~java
List<String> raw = Arrays.asList(
        "Java", null, "Stream", null, "NIO");

List<String> clean = raw.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());

// clean == ["Java", "Stream", "NIO"].
~~~

Đây là **đoạn minh họa** cần thêm import `Collectors`.

Dòng `filter(Objects::nonNull)` tương đương về logic với:

~~~java
.filter(item -> item != null)
~~~

Với null-only filter, **không nên tuyên bố method reference luôn nhanh hơn lambda**. JIT có thể tối ưu cả hai; chọn cách dễ đọc, và benchmark nếu hot path thật sự là vấn đề.

### 3.1. Objects::isNull giữ lại phần tử thiếu

~~~java
long missingCount = numbers.stream()
        .filter(Objects::isNull)
        .count();

// missingCount == 2.
~~~

Vì `isNull` trả true chính xác cho những tham chiếu null, `filter` sẽ **giữ null**, sau đó `count()` cho biết số phần tử null. Pattern này thường hữu ích để đo tỷ lệ thiếu dữ liệu trước khi tính thống kê.

### 3.2. Stream.filter là intermediate operation

~~~java
Stream<Integer> pipeline = numbers.stream()
        .filter(Objects::nonNull);
~~~

`filter` là **lazy**: không có chuyện toàn bộ danh sách lập tức bị lọc khi tạo pipeline. Các phần tử được xử lý khi chạy terminal operation như `collect`, `count`, `sum` hay `forEach`.

Đồng thời, `filter` **không sửa danh sách gốc**. Nếu `numbers` ban đầu vẫn chứa null, sau `collect` nó vẫn giữ các phần tử ấy, trừ khi code bên ngoài thực sự biến đổi danh sách.

### 3.3. Stream một lần dùng

Một instance `Stream` không được dùng lặp terminal operations:

~~~java
// PHẢN VÍ DỤ:
Stream<Integer> stream = numbers.stream()
        .filter(Objects::nonNull);
long count = stream.count();
// long total = stream.mapToInt(Integer::intValue).sum(); // Sai: reuse.
~~~

Để tính hai thống kê, tạo stream mới từ collection hoặc dùng collector/tập dữ liệu trung gian phù hợp.

### 3.4. Null element khác null stream

~~~java
Stream<String> oneMissing = Stream.of((String) null);
long elements = oneMissing.count(); // 1.
~~~

`Stream.of((String)null)` là một stream **có một phần tử null**, không phải stream rỗng. Ngược lại:

~~~java
Stream<String> empty = Stream.empty();
long elements = empty.count(); // 0.
~~~

Và nếu **biến chứa collection** là null, gọi `collection.stream()` sẽ NPE **trước khi** `filter` có cơ hội chạy. `Objects::nonNull` chỉ lọc phần tử **sau khi đã có Stream hợp lệ**, không bảo vệ mọi tầng.

## 4. Số 0, thiếu dữ liệu, dữ liệu không hợp lệ: ba trạng thái

Danh sách:

~~~text
[null, 0, 12, null, -3, 5]
~~~

Có tổng 6 vị trí:

| Thống kê | Kết quả | Vì sao |
| --- | --- | --- |
| Tổng vị trí | 6 | Bao gồm cả missing |
| Số missing | 2 | Hai giá trị null |
| Số present | 4 | 0,12,-3,5 |
| Tổng present | 14 | 0+12−3+5 |
| Trung bình present | 3.5 | 14/4 |
| Tổng positive only | 17 | 12+5 |
| Số giá trị bằng zero | 1 | Zero là số hợp lệ |
| Số giá trị âm | 1 | -3 vẫn present |

Nếu business muốn “null được coi là 0”, trung bình theo **6 vị trí** sẽ là 14/6, **khác** 14/4. Không dùng `filter(Objects::nonNull)` rồi tuyên bố mẫu số vẫn là số lượng bản ghi ban đầu.

### 4.1. Loại thiếu không đồng nghĩa tự gán zero

~~~java
List<Integer> present = numbers.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
~~~

Đoạn này bỏ hai phần tử missing. Nó **không** tạo `0` để lấp vào hai vị trí. Nếu thuật toán cần số phần tử bằng nhau với dữ liệu gốc, việc loại phần tử có thể làm sai alignment với danh sách timestamp tương ứng.

### 4.2. Gán zero mặc định có thể làm biến đổi ý nghĩa

~~~java
List<Integer> withZeroDefault = numbers.stream()
        .map(n -> n == null ? 0 : n)
        .collect(Collectors.toList());

// [0, 0, 12, 0, -3, 5].
~~~

Đây là code Java 8 hợp lệ, nhưng nó làm mất khả năng phân biệt “đã quan sát số 0” với “không có quan sát”. Chỉ làm như vậy **nếu domain rule định nghĩa missing là zero**, không tự động vì thuận tiện cho `sum`.

### 4.3. Dữ liệu lỗi đôi khi phải reject, không lọc

Nếu một trong các số là **giá giao dịch**, một mục null có thể chỉ ra lỗi nhập thiếu giá. Im lặng loại mục rồi cộng phần còn lại sẽ tạo báo cáo sai mà không có exception. Thay vào đó, hãy kiểm tra input và báo lỗi tường minh khi dữ liệu bắt buộc.

### 4.4. Phân loại dữ liệu thay vì chỉ có boolean

Trong hệ thống thực, nhiều tình huống cần phân loại:

- PRESENT: có giá trị số (kể cả zero/âm).
- MISSING: không có số.
- INVALID: có value nhưng vi phạm schema, chẳng hạn số âm ở trường không được âm, hoặc NaN nếu domain không cho phép.

`Objects.nonNull` chỉ phân biệt PRESENT-REFERENCE và NULL. Muốn phân loại INVALID, phải có predicates bổ sung và không tự đánh đồng null với invalid.

## 5. Lọc trước khi unbox và tính toán

### 5.1. Autounboxing của wrapper null gây NPE

~~~java
Integer amount = null;

// PHẢN VÍ DỤ:
int value = amount; // NullPointerException khi unbox.
~~~

Trong pipeline:

~~~java
// PHẢN VÍ DỤ nếu numbers chứa null:
long sum = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

`Integer::intValue` phải được gọi trên mỗi phần tử. Khi phần tử null, method invocation/unboxing thất bại với `NullPointerException`.

**Cách đúng khi policy cho phép bỏ missing:**

~~~java
long sum = numbers.stream()
        .filter(Objects::nonNull)
        .mapToLong(Integer::longValue)
        .sum();
~~~

Ở đây null filter diễn ra **trước** khi gọi method trên Integer. `mapToLong` cho phép tích lũy kiểu `long` thay vì `int`, giảm rủi ro tràn số khi tổng vượt miền int, nhưng **không loại bỏ nguy cơ overflow long** nếu dữ liệu cực lớn.

### 5.2. mapToInt dùng khi miền kết quả đủ

~~~java
int sum = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
~~~

Phép cộng trên int **có thể overflow** khi tổng lớn hơn `Integer.MAX_VALUE` hoặc nhỏ hơn `Integer.MIN_VALUE`. Đừng cho rằng việc lọc null tự giải quyết độ chính xác số học.

### 5.3. Trung bình và OptionalDouble

~~~java
OptionalDouble average = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .average();

if (average.isPresent()) {
    System.out.println(average.getAsDouble()); // 3.5
}
~~~

`IntStream.average()` trả `OptionalDouble` vì một stream không có giá trị có **trung bình không xác định** theo cách hiểu thông thường.

Khi mọi giá trị đều null:

~~~java
OptionalDouble none = Arrays.asList(
        (Integer) null, (Integer) null).stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .average();

// none.isPresent() == false.
~~~

Không gọi `getAsDouble()` trên `OptionalDouble.empty()`. Cũng không mặc định `orElse(0.0)` là quyết định thống kê đúng; chỉ dùng fallback zero khi business rule muốn vậy.

### 5.4. Count và average phải sử dụng cùng chính sách lọc

Nếu cần số mẫu và trung bình, hãy xác định mẫu đang được dùng: chỉ giá trị present, chỉ positive, hoặc cả zero. Ví dụ:

~~~java
long presentCount = numbers.stream()
        .filter(Objects::nonNull)
        .count();

double average = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .average()
        .orElse(Double.NaN);
~~~

Đây là minh họa policy hiển thị: khi không có mẫu, dùng NaN để biểu thị “không có trung bình” **chỉ khi downstream xử lý được NaN**. Một domain model dùng `OptionalDouble` thường rõ ràng hơn khi thiếu dữ liệu.

### 5.5. Primitive streams không chứa null

`IntStream`, `LongStream` và `DoubleStream` chứa primitive numeric values, không có phần tử null. Do đó:

~~~java
// PHẢN VÍ DỤ: IntStream.filter cần IntPredicate,
// không nhận Objects::nonNull cho một int element.
// IntStream.of(1, 2, 3).filter(Objects::nonNull);
~~~

Chỉ dùng `Objects::nonNull` **trên Stream của reference types** như `Stream<Integer>`, `Stream<Double>` hoặc `Stream<Record>`; sau khi đã chuyển sang primitive stream, không còn null để lọc.

## 6. Vị trí của filter trong pipeline quyết định tính an toàn

### 6.1. Đúng: lọc trước method có thể dereference

~~~java
List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());
~~~

Nếu `raw = [" A ", null, "  ", "B"]`, kết quả là `["A", "B"]`.

Giải thích:

1. `Objects::nonNull` bỏ null.
2. `String::trim` chỉ chạy trên String không null.
3. `isEmpty` loại String rỗng sau trim.
4. `collect` tạo List mới.

### 6.2. Sai: map trước khi lọc phần tử null

~~~java
// PHẢN VÍ DỤ khi raw chứa null:
raw.stream()
        .map(String::trim)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
~~~

`String::trim` dereference null và NPE **trước** khi filter. Đặt filter ở cuối không sửa được lỗi xảy ra ở bước trước.

### 6.3. Mapper có thể tạo ra null mới

Ngay cả khi đã lọc phần tử đầu vào, một mapper có thể trả null:

~~~java
List<String> normalized = rows.stream()
        .filter(Objects::nonNull)
        .map(Row::getLabel)
        .filter(Objects::nonNull)
        .map(String::trim)
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa**, giả định class `Row` có getter `getLabel()` trả `String` nullable. Bộ lọc thứ nhất bảo vệ `Row::getLabel`, bộ lọc thứ hai bảo vệ `String::trim`.

**Điểm cần nhớ:** `filter(Objects::nonNull)` không phải chứng minh từ đầu đến cuối rằng **mọi bước sau luôn non-null**, vì bước `map` có thể sinh null mới.

### 6.4. Method reference không có quyền kiểm tra nested field tự động

~~~java
// PHẢN VÍ DỤ: user object không null nhưng user.getAge() có thể null.
users.stream()
        .filter(Objects::nonNull)
        .mapToInt(user -> user.getAge())
        .sum();
~~~

Nếu `getAge()` trả `Integer` null, mapToInt sẽ unbox và NPE. Cần biểu diễn rõ:

~~~java
users.stream()
        .filter(Objects::nonNull)
        .map(User::getAge)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
~~~

Hai đoạn là **minh họa** về class `User` có getter trả Integer nullable. Không có class User trong chương trình độc lập, nên không copy hai fragment vào một file mà chưa khai báo model.

### 6.5. Không dùng peek để “sửa null”

`Stream.peek` chủ yếu để quan sát/debug, không phải nơi áp dụng business transformation và side effect quan trọng. Viết `peek(x -> ...)` rồi dựa vào thứ tự/số lần callback để sửa collection đang stream có thể sai, nhất là khi short-circuit/parallel.

Dùng `map` để biến đổi, `filter` để chọn/loại, `collect` để tổng hợp theo contract.

## 7. Lọc record có field nullable: hai cấp dữ liệu

Ví dụ một record:

~~~java
static final class Reading {
    final String group;
    final Integer value;

    Reading(String group, Integer value) {
        this.group = group;
        this.value = value;
    }
}
~~~

Mẫu dữ liệu:

~~~text
Reading("math", 10)
null
Reading("math", null)
Reading("science", 0)
Reading(null, 7)
Reading("science", -2)
~~~

Cần phân biệt:

1. **Cả Reading object là null**.
2. **Reading tồn tại nhưng `value` null**.
3. **Reading tồn tại nhưng `group` null**.
4. **Reading có `value=0`**, hoàn toàn khác missing.

### 7.1. Lấy các giá trị số hợp lệ

~~~java
List<Integer> values = readings.stream()
        .filter(Objects::nonNull)
        .map(r -> r.value)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());

// [10, 0, 7, -2].
~~~

Lưu ý record với `group=null` **vẫn có số 7**. Việc có bỏ nó khỏi **tổng giá trị số** hay không là domain rule; không tự bỏ theo group vì hai mục tiêu lọc khác nhau.

### 7.2. Grouping theo group name: bỏ khóa null nếu policy như vậy

~~~java
Map<String, Long> groupCounts = readings.stream()
        .filter(Objects::nonNull)
        .filter(r -> Objects.nonNull(r.group))
        .collect(Collectors.groupingBy(
                r -> r.group, TreeMap::new,
                Collectors.counting()));

// {math=2, science=2}
~~~

Đây là đoạn minh họa Java 8, cần imports `Map`, `TreeMap`, `Collectors`. Những record có `group=null` hoặc cả record null bị loại khỏi grouping. Một Reading có `value=null` vẫn được đếm vì yêu cầu thống kê **số record theo group**, không phải số record có giá trị số.

### 7.3. Cần group theo record có value hợp lệ? Thêm điều kiện riêng

~~~java
Map<String, Long> validCounts = readings.stream()
        .filter(Objects::nonNull)
        .filter(r -> r.group != null && r.value != null)
        .collect(Collectors.groupingBy(
                r -> r.group, TreeMap::new,
                Collectors.counting()));
~~~

Ở ví dụ mẫu, `math=1`, `science=2`. `&&` trong Java có short-circuit, nên check `r.value!=null` chỉ chạy sau khi `r.group!=null` không có vấn đề; cả hai fields đều được kiểm tra tường minh.

**Khác thống kê:** “bao nhiêu records mỗi group” và “bao nhiêu records có số hợp lệ mỗi group” không phải cùng một số.

### 7.4. Tránh rơi vào NPE khi gọi equals

~~~java
// PHẢN VÍ DỤ nếu r.group là null:
r.group.equals("math")
~~~

Thay bằng:

~~~java
"math".equals(r.group)
~~~

nếu r đã non-null, hoặc:

~~~java
Objects.equals(r.group, "math")
~~~

Cả hai đều null-safe với field group. Cách dùng phụ thuộc readability và chính sách domain, nhưng không nên cố lọc null ở chỗ khác rồi giả định mọi nested reference đã được bảo vệ.

## 8. Stream terminal operations có thể vẫn nhạy cảm với null

### 8.1. findFirst và findAny

~~~java
// PHẢN VÍ DỤ: phần tử đầu là null.
Stream.of((String) null, "A").findFirst();
~~~

`Stream.findFirst()` trả `Optional<T>` và ném `NullPointerException` nếu phần tử được chọn là null theo Javadoc. Vì vậy, nếu stream có null:

~~~java
Optional<String> first = Stream.of((String) null, "A")
        .filter(Objects::nonNull)
        .findFirst();

// first.get().equals("A") == true.
~~~

Với `findAny()`, phần tử được chọn có thể phụ thuộc lịch chạy khi stream không có order cố định; lọc nonNull trước nếu cần chắc chắn không nhận null.

### 8.2. min/max và các bộ sưu tập khác

Một số terminal operations chứa cơ chế bọc result bằng Optional, nên kết quả null có thể gây NPE. Với numeric values có null, **lọc** trước khi dùng `min`, `max` hoặc primitive numeric reductions.

### 8.3. Collector.toList có thể chứa null

~~~java
List<String> list = Stream.of(
        (String) null, "A").collect(Collectors.toList());

// List có thể chứa phần tử null (với collector toList Java 8).
~~~

Collector `toList` không tự trở thành null filter. Nếu policy muốn List toàn non-null, phải viết `filter(Objects::nonNull)`.

### 8.4. groupingBy với classifier trả null

~~~java
// PHẢN VÍ DỤ trong Java 8:
Stream.of("A", (String) null)
        .collect(Collectors.groupingBy(s -> s));
~~~

Trong triển khai/hợp đồng `Collectors.groupingBy` của Java 8, classifier trả null gây `NullPointerException`. Chương trình đầy đủ ở mục 17 kiểm chứng điều này.

Nếu key là optional field, cần:

- Bỏ các record có key null **nếu business cho phép**.
- Hoặc ánh xạ sang một nhóm sentinel **có định nghĩa rõ**, ví dụ `"UNKNOWN"`, nhưng phải bảo đảm sentinel không va chạm tên thật hoặc dùng kiểu key riêng.
- Không cho rằng Map implementation cho phép null key thì `groupingBy` cũng nhất định cho phép classifier null.

### 8.5. toMap và null values

`Collectors.toMap` trong nhiều trường hợp từ chối null mapped values và cũng có chính sách về **duplicate keys**. Đừng cố dùng nó như phép “gom mọi null tự động” từ records chưa chuẩn hóa. Lọc/validate key và value trước, đồng thời cung cấp merge function khi dữ liệu có thể trùng keys.

## 9. Objects::isNull dùng để kiểm tra chất lượng dữ liệu

Khi yêu cầu là đếm missing, cần giữ nguyên thông tin về dữ liệu nguồn.

### 9.1. Đếm null trực tiếp

~~~java
long missing = numbers.stream()
        .filter(Objects::isNull)
        .count();
~~~

Đây là cách dễ đọc, nhưng không cần gọi stream nếu một vòng for đơn giản phù hợp hơn. Đặc biệt khi cần vừa đếm missing vừa cộng present, có thể duyệt một lần để tránh nhiều traversals.

### 9.2. Partition missing và present

~~~java
Map<Boolean, List<Integer>> buckets = numbers.stream()
        .collect(Collectors.partitioningBy(Objects::isNull));

List<Integer> missingValues = buckets.get(true);
List<Integer> presentValues = buckets.get(false);
~~~

`partitioningBy` chia stream thành hai bucket theo predicate. **Bucket true chứa những phần tử null**, còn bucket false chứa số hiện diện. Cách này giữ lại phân loại nhưng vẫn cần cẩn trọng nếu collect một tập rất lớn vào RAM.

Với dữ liệu nguồn mẫu, true bucket có 2 null, false bucket chứa `[0,12,-3,5]`.

### 9.3. Đếm theo partition mà không lưu toàn bộ dữ liệu

~~~java
Map<Boolean, Long> counts = numbers.stream()
        .collect(Collectors.partitioningBy(
                Objects::isNull, Collectors.counting()));

long missing = counts.get(true);
long present = counts.get(false);
~~~

Đây là một lần traversal để đếm hai nhóm. Với dữ liệu lớn, nó tránh tạo hai danh sách trong memory. Không dùng Map iteration order để in deterministic output; lấy rõ keys `true` và `false`.

### 9.4. Dấu hiệu chất lượng có thể quan trọng hơn tổng

Khi kiểm tra một batch cảm biến, tổng các sample present có thể ổn nhưng số phần tử missing rất lớn. Hãy báo cả:

- Tổng số observations.
- Số present và missing.
- Tỷ lệ completeness, theo mẫu số chính xác.
- Các giá trị ngoài miền cho phép (âm, quá ngưỡng).
- Lỗi schema/parse riêng với null đã hợp lệ.

Không “xóa dấu vết thiếu dữ liệu” bằng cách chỉ lưu kết quả của `filter(nonNull)` nếu ứng dụng cần audit chất lượng đầu vào.

## 10. Sắp xếp null: loại bỏ hay giữ lại?

### 10.1. Lọc rồi sort

Nếu mục tiêu chỉ lấy các giá trị present:

~~~java
List<Integer> sortedPresent = numbers.stream()
        .filter(Objects::nonNull)
        .sorted()
        .collect(Collectors.toList());
~~~

Với dữ liệu mẫu, kết quả là `[-3,0,5,12]`. Null bị loại và **số vị trí thay đổi**.

### 10.2. Giữ null và đặt xuống cuối

Nếu business cần **giữ số lượng phần tử**, ví dụ bảng nhập liệu có missing cần hiển thị ở cuối:

~~~java
List<Integer> input = new ArrayList<>(
        Arrays.asList(3, null, -1, null, 0));

input.sort(Comparator.nullsLast(Comparator.naturalOrder()));

// [-1, 0, 3, null, null].
~~~

Đây là Java 8, cần import `ArrayList` và `Comparator`. `Comparator.nullsFirst` cũng có thể đưa null lên đầu.

**Khác nhau về dữ liệu:** Sort với comparator null-safe **không xóa null**, còn `filter(Objects::nonNull)` xóa chúng khỏi kết quả.

### 10.3. Không tự dùng Comparator.naturalOrder với null

~~~java
// PHẢN VÍ DỤ nếu input có null:
input.sort(Comparator.naturalOrder());
~~~

`naturalOrder` không hỗ trợ null. Nếu không loại null, dùng `Comparator.nullsFirst/nullsLast` với comparator thích hợp.

### 10.4. Null ordering phải có business meaning

Đừng tự dùng “null nhỏ hơn mọi số” cho báo cáo tài chính/scoreboard nếu domain không quy định. Thường bảng dữ liệu hiển thị missing ở cuối, nhưng tính thống kê phải theo sample policy rõ ràng.

## 11. BigDecimal và tiền: null khác 0.00

Trong các nghiệp vụ tiền tệ, một số tiền chưa nhập **không tự bằng 0**. Nếu được phép bỏ số liệu thiếu để thống kê, `Objects::nonNull` có thể dùng với `BigDecimal`:

~~~java
List<BigDecimal> amounts = Arrays.asList(
        new BigDecimal("1.20"),
        null,
        new BigDecimal("-0.20"),
        new BigDecimal("3.00"));

BigDecimal total = amounts.stream()
        .filter(Objects::nonNull)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

// total.toPlainString().equals("4.00") == true.
~~~

`BigDecimal` giữ phép toán thập phân theo scale/rules phù hợp và tránh sai số từ phép cộng `double` khi dùng đúng. Nhưng:

- Bỏ null chỉ đúng nếu **missing được phép bỏ**.
- Nếu mỗi record bắt buộc có amount, cần **reject null** chứ không lọc.
- `BigDecimal.ZERO` là identity cho phép cộng, **không chứng minh** đã có ít nhất một giá trị.
- Scale và rounding cần quy định khi phép toán phức tạp, ví dụ chia trung bình số tiền.
- Numeric total không tự thay thế transaction/ledger correctness.

### 11.1. Coi null bằng ZERO có thể sai

~~~java
List<BigDecimal> replaced = amounts.stream()
        .map(a -> a == null ? BigDecimal.ZERO : a)
        .collect(Collectors.toList());
~~~

Đây là Java 8 minh họa. Nó biến một record thiếu amount thành một record amount=0. Nếu hệ thống dùng để thanh toán, chuyển đổi này cần explicit domain rule, không nên thực hiện vì mục tiêu “không cho NPE”.

### 11.2. Empty sum vs no data

`Stream<BigDecimal>` rỗng khi reduce với `BigDecimal.ZERO` trả ZERO. Về mặt số học, identity hợp lệ; về mặt thống kê, kết quả ZERO có thể **không phân biệt** “không có mẫu” với “có mẫu nhưng tổng bằng 0”. Khi cần phân biệt, trả thêm presentCount hoặc một result type có trạng thái.

## 12. Double.NaN và Infinity không phải null

### 12.1. Objects.nonNull không lọc NaN

~~~java
List<Double> samples = Arrays.asList(
        1.5, null, Double.NaN,
        Double.POSITIVE_INFINITY, 2.5);
~~~

Sau `filter(Objects::nonNull)`, stream vẫn chứa `Double.NaN` và `POSITIVE_INFINITY` vì chúng là những object Double có giá trị.

~~~java
double sum = samples.stream()
        .filter(Objects::nonNull)
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

Phép cộng với NaN thường cho NaN. Nếu business yêu cầu **chỉ số hữu hạn**, phải thêm predicate:

~~~java
double finiteSum = samples.stream()
        .filter(Objects::nonNull)
        .filter(Double::isFinite)
        .mapToDouble(Double::doubleValue)
        .sum();

// finiteSum == 4.0.
~~~

`Double.isFinite(double)` có từ Java 8, trả false với NaN và infinities. Method reference `Double::isFinite` ở stream Double được Java tự unbox để kiểm tra primitive double; chạy được ở Java 8.

### 12.2. Thiếu không đồng nghĩa không hữu hạn

Có ít nhất ba nhóm phải phân loại khác nhau:

- Null: không có Double object.
- Non-null nhưng non-finite: NaN/positive infinity/negative infinity.
- Non-null và finite: giá trị thực phù hợp miền biểu diễn.

Nếu API trả dữ liệu môi trường có thể chứa NaN/Infinity, filter non-null **chưa đủ**. Hãy xác định rõ có cho bỏ non-finite không hay phải fail validation.

### 12.3. Floating-point sum không luôn chính xác thập phân

Ngay cả khi đã lọc null và non-finite, phép cộng `double` vẫn có vấn đề làm tròn nhị phân và thứ tự cộng trong parallel stream. Đối với tiền hoặc số cần chính xác thập phân, xem xét `BigDecimal` và quy định scale/rounding.

## 13. Optional: biểu diễn giá trị có thể vắng mặt, không phải bộ lọc toàn diện

### 13.1. Optional.ofNullable

~~~java
Optional<Integer> maybe = Optional.ofNullable(possiblyNull);

Integer result = maybe.orElse(0);
~~~

Đây là **đoạn minh họa**, cần `possiblyNull` được khai báo và import `Optional`. `Optional.ofNullable(null)` trả `Optional.empty()` thay vì ném exception; nó hữu ích để biểu diễn một giá trị có thể vắng mặt.

Nhưng `orElse(0)` vẫn **biến missing thành zero ở tầng kết quả**. Chỉ dùng khi rule cho phép, không nên coi đó là mặc định nghiệp vụ.

### 13.2. Optional.of khác ofNullable

~~~java
Optional.of(null);         // Ném NullPointerException.
Optional.ofNullable(null); // Optional.empty().
~~~

`Optional.of` phù hợp khi tham số được yêu cầu chắc chắn non-null. Khi nullable hợp lệ, `ofNullable` phù hợp hơn.

### 13.3. Optional.empty khác Stream rỗng và Stream chứa null

- `Optional.empty()`: một container “không có giá trị”.
- `Stream.empty()`: một chuỗi phần tử rỗng.
- `Stream.of((String)null)`: chuỗi có **một phần tử null**.

Không nhầm các abstraction này khi thiết kế APIs.

### 13.4. Java 8 chưa có Stream.ofNullable

`Stream.ofNullable(value)` được giới thiệu **sau Java 8** (Java 9), và vẫn còn dùng ở các phiên bản Java hiện hành, nhưng **không thể biên dịch với `--release 8`**. Với module Java 8, chỉ dùng `filter(Objects::nonNull)` trên stream đã có, hoặc các patterns Java 8 khác được thiết kế rõ ràng.

Tránh sao chép đoạn code từ bài Java 17 vào build Java 8 rồi thắc mắc vì sao IDE báo “cannot find symbol”.

### 13.5. Không nên dùng Optional làm vật chứa mọi field

Optional hữu ích cho **return type có thể thiếu**, nhưng việc đưa Optional vào mọi field/collection không tự giải quyết schema hay serialization. Nếu record có nhiều trạng thái missing/invalid/zero, một domain model rõ ràng và contract validation có thể diễn đạt tốt hơn.

## 14. Objects.requireNonNull cho dữ liệu bắt buộc, Objects.nonNull cho dữ liệu tùy chọn

### 14.1. Parameter bắt buộc

~~~java
public static int requirePort(Integer port) {
    return Objects.requireNonNull(port, "port is required");
}
~~~

Đây là method của chương trình runnable ở mục 17. Với port null, nó ném `NullPointerException` có thông điệp rõ; với `port=0`, nó trả 0 (vì null check không biết 0 có hợp lệ làm port theo domain hay không).

Nếu business yêu cầu port trong khoảng 1 đến 65535, cần **validation số** riêng:

~~~java
if (port == null || port < 1 || port > 65535) {
    throw new IllegalArgumentException("invalid port");
}
~~~

`Objects.requireNonNull` bảo vệ null, không kiểm tra khoảng.

### 14.2. Dữ liệu thiếu hợp lệ trong pipeline

Một hệ thống log lưu optional latency:

~~~java
long latencySum = latencies.stream()
        .filter(Objects::nonNull)
        .mapToLong(Long::longValue)
        .sum();
~~~

Đây là **đoạn minh họa** với `List<Long> latencies`. Không có lý do ném exception nếu từng missing là hợp lệ theo domain, nhưng kết quả nên đi kèm sampleCount/completeness.

### 14.3. Không nhầm exception với loại bỏ

- `requireNonNull`: **từ chối** dữ liệu null bằng exception.
- `filter(Objects::nonNull)`: **bỏ qua** dữ liệu null khỏi stream kết quả.
- `map(n -> n==null?fallback:n)`: **điền giá trị thay thế**.
- `partitioningBy(Objects::isNull)`: **phân loại** missing/present.

Bốn hành vi mang nghĩa nghiệp vụ khác nhau. Chọn hành vi trước khi tối ưu cú pháp.

## 15. Đầu vào từ JDBC, JSON, CSV và tính nhất quán dữ liệu

### 15.1. Java Integer có thể biểu diễn null, int thì không

Một cột database nullable có thể được ánh xạ vào `Integer`. Nếu code chuyển thẳng sang `int`, null bị unbox và NPE hoặc một mapper nào đó có thể áp default sai.

Khi đọc JDBC primitive getter như `ResultSet.getInt`, giá trị SQL NULL thường được biểu diễn là 0 và cần gọi `wasNull()` để phân biệt. Đây là **điểm quan trọng với bài toán số học**: đừng cho rằng 0 từ JDBC luôn là số 0 thật của database.

~~~java
int value = rs.getInt("amount");
boolean missing = rs.wasNull();
~~~

Đây là **đoạn minh họa** trong ngữ cảnh có `ResultSet rs`, không phải source độc lập. `wasNull()` phải được dùng đúng sau getter cần kiểm tra theo contract JDBC.

### 15.2. JSON null khác omitted field

Trong JSON, một thuộc tính có giá trị `null` và một thuộc tính **không hiện diện** có thể khác nhau theo schema. Nhiều Java mappers có policy riêng về default values. Khi nhận DTO, xác định rõ các states:

~~~text
{"amount": 0}      -> giá trị hiện diện và bằng 0
{"amount": null}   -> trường hiện diện nhưng null
{}                 -> trường không được cung cấp
~~~

Đây là **JSON minh họa**, không nhất thiết được một DTO mapper cụ thể phân biệt nếu model không thiết kế thêm presence flag. `Objects.nonNull(amount)` trên DTO chỉ biết reference hiện tại, không biết field đã có trong JSON gốc hay bị omit.

### 15.3. CSV “trống” không tự là null

Một CSV parser có thể trả `""` cho ô trống, không phải `null`. `Objects.nonNull("")` trả true. Để chuyển text thành số, cần trim, kiểm tra blank, parse và phân loại lỗi.

~~~java
String token = "   ";
boolean blank = token.trim().isEmpty(); // true
boolean present = Objects.nonNull(token); // true
~~~

Trong Java 8, `String.isBlank()` chưa có; nếu target Java 8, dùng logic phù hợp như `trim` (lưu ý Unicode whitespace semantics không hoàn toàn giống `isBlank` trên Java mới).

### 15.4. Lọc không thay thế validate parse

`Objects.nonNull("abc")` true, nhưng `Integer.parseInt("abc")` ném `NumberFormatException`. Nếu API nhận dữ liệu numeric dạng text, cần phân biệt null, blank và malformed number, không chỉ một non-null predicate.

### 15.5. Cẩn trọng khi dùng dữ liệu ngoài tin cậy

Đối với thanh toán/định danh/giới hạn quota, “bỏ giá trị invalid và tiếp tục” có thể tạo ra kết quả nguy hiểm. Lọc chỉ nên diễn ra khi business cho phép incomplete data; nếu không, phải fail validation và báo nguyên nhân.

## 16. Hiệu năng, đọc hiểu và xử lý song song

### 16.1. Lọc null là thao tác rẻ nhưng pipeline còn nhiều chi phí khác

`Objects.nonNull` chỉ là một tham chiếu null check. Với tập dữ liệu nhỏ, một vòng for đơn giản có thể dễ debug và có hiệu năng cạnh tranh; Stream pipeline có lợi về cách diễn đạt compositional transformations.

~~~java
long sum = 0L;
long missing = 0L;

for (Integer n : numbers) {
    if (n == null) {
        missing++;
    } else {
        sum += n.longValue();
    }
}
~~~

Đoạn Java 8 minh họa này vừa cộng present vừa đếm missing trong **một lượt**, không cần tạo stream hai lần. Dùng nó khi việc phải báo cả hai chỉ số hoặc performance profile khiến vòng loop rõ ràng hơn.

### 16.2. Không tuyên bố method reference luôn nhanh

`filter(Objects::nonNull)` và `filter(x -> x != null)` có logic giống nhau. JIT, inlining, boxing, allocation và workload sẽ quyết định tốc độ. Đừng chọn dựa trên microbenchmark thiếu warmup. Nếu có contention hoặc hot path thật, dùng benchmark phù hợp như JMH.

### 16.3. Tránh boxing khi có thể

Nếu dữ liệu vốn có thể được lưu trong `int[]` và **không cần thiếu/nullable**, `IntStream` hoặc vòng for trên primitive tránh overhead boxing. Nếu dữ liệu thực sự có missing, phải có một data model biểu diễn presence (ví dụ wrapper, bitset, optional marker) và cân nhắc footprint.

Không dùng một magic number như `-1` làm null thay thế nếu `-1` có thể là giá trị hợp lệ.

### 16.4. Parallel streams không tự bảo đảm correctness từ mutable source

`Objects::nonNull` là predicate stateless, phù hợp cho parallel pipeline. Nhưng nếu List nguồn bị thread khác sửa đồng thời mà không có contract concurrency phù hợp, đọc stream có thể cho kết quả không nhất quán hoặc exception. Không cho rằng thêm `parallelStream` tạo snapshot hay thread safety.

### 16.5. Không mutate nguồn trong filter

~~~java
// PHẢN VÍ DỤ: side effect và interference với nguồn.
numbers.stream()
        .filter(n -> {
            numbers.remove(n);
            return n != null;
        })
        .count();
~~~

Source có thể bị sửa giữa traversal, gây lỗi hoặc kết quả bất định. Dùng một pipeline thuần tạo List mới, hoặc sửa collection bằng method thiết kế riêng như `removeIf` khi thực sự muốn biến đổi nguồn và có chính sách mutability/concurrency rõ.

### 16.6. API tách filtering và persistence

Nếu dữ liệu được dùng cho audit, nên giữ raw input hoặc record về số missing cùng cleaned result. Một stream filtered tạo ra object list mới nhưng **không giải thích vì sao mất record** trừ khi logging/metadata được thiết kế.

## 17. Chương trình Java 8 chạy độc lập, có stdout được xác minh

Chương trình **NullFilteringArithmeticDemo.java** dưới đây minh họa đầy đủ:

1. `Objects.isNull`, `Objects.nonNull` cho null và zero.
2. Lọc List<Integer> chứa hai null, tính missing count, total, average, positive sum.
3. Empty average không giả làm zero.
4. Unboxing null gây NPE; lọc trước khi unbox.
5. Làm sạch String sau khi lọc null.
6. Lọc record null và field value nullable ở hai bước.
7. Grouping bỏ null group key và đếm records.
8. Sort giữ null ở cuối bằng comparator null-safe.
9. Tổng BigDecimal có nullable amount.
10. Double finite filter xử lý NaN/Infinity.
11. Phân biệt Stream có một null với Stream rỗng.
12. `Objects.requireNonNull` để validate tham số và `Collectors.groupingBy` từ chối null key.

Lưu thành **NullFilteringArithmeticDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class NullFilteringArithmeticDemo {
    static final class Reading {
        final String group;
        final Integer value;

        Reading(String group, Integer value) {
            this.group = group;
            this.value = value;
        }
    }

    static int requirePort(Integer port) {
        return Objects.requireNonNull(port, "port is required");
    }

    public static void main(String[] args) {
        System.out.println("isNull(null) = " + Objects.isNull(null));
        System.out.println("nonNull(null) = " + Objects.nonNull(null));
        System.out.println("nonNull(0) = " + Objects.nonNull(0));

        List<Integer> numbers =
                Arrays.asList(null, 0, 12, null, -3, 5);
        List<Integer> present = numbers.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        System.out.println("present = " + present);
        System.out.println("missing count = " + numbers.stream()
                .filter(Objects::isNull).count());
        System.out.println("present count = " + present.size());
        long total = numbers.stream()
                .filter(Objects::nonNull)
                .mapToLong(Integer::longValue)
                .sum();
        System.out.println("sum = " + total);
        OptionalDouble average = numbers.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .average();
        System.out.println("average = " + average.getAsDouble());
        System.out.println("positive sum = " + numbers.stream()
                .filter(Objects::nonNull)
                .filter(n -> n > 0)
                .mapToLong(Integer::longValue).sum());

        List<Integer> onlyMissing = Arrays.asList(null, null);
        OptionalDouble absentAverage = onlyMissing.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .average();
        System.out.println("all missing average present = "
                + absentAverage.isPresent());

        try {
            numbers.stream().mapToInt(Integer::intValue).sum();
            System.out.println("unboxing null rejected = false");
        } catch (NullPointerException expected) {
            System.out.println("unboxing null rejected = true");
        }

        List<String> raw = Arrays.asList(" A ", null, "  ", "B");
        List<String> cleaned = raw.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toList());
        System.out.println("trimmed nonblank = " + cleaned);

        List<Reading> readings = Arrays.asList(
                new Reading("math", 10),
                null,
                new Reading("math", null),
                new Reading("science", 0),
                new Reading(null, 7),
                new Reading("science", -2));
        List<Integer> values = readings.stream()
                .filter(Objects::nonNull)
                .map(r -> r.value)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        System.out.println("nested present values = " + values);
        System.out.println("nested sum = "
                + values.stream().mapToLong(Integer::longValue).sum());
        Map<String, Long> byGroup = readings.stream()
                .filter(Objects::nonNull)
                .filter(r -> Objects.nonNull(r.group))
                .collect(Collectors.groupingBy(
                        r -> r.group, TreeMap::new, Collectors.counting()));
        System.out.println("group counts = " + byGroup);

        List<Integer> withNulls =
                new ArrayList<>(Arrays.asList(3, null, -1, null, 0));
        withNulls.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("sorted with nulls last = " + withNulls);

        List<BigDecimal> amounts = Arrays.asList(
                new BigDecimal("1.20"),
                null,
                new BigDecimal("-0.20"),
                new BigDecimal("3.00"));
        BigDecimal money = amounts.stream()
                .filter(Objects::nonNull)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("decimal sum = " + money.toPlainString());

        List<Double> samples = Arrays.asList(
                1.5, null, Double.NaN,
                Double.POSITIVE_INFINITY, 2.5);
        System.out.println("numeric finite sum = " + samples.stream()
                .filter(Objects::nonNull)
                .filter(Double::isFinite)
                .mapToDouble(Double::doubleValue).sum());

        System.out.println("one null is an element = "
                + Stream.of((String) null).count());
        System.out.println("zero is kept = " + present.contains(0));
        System.out.println("missing is not zero = "
                + (numbers.stream().filter(Objects::isNull).count() > 0
                   && present.contains(0)));
        System.out.println("valid port = " + requirePort(8080));
        try {
            requirePort(null);
            System.out.println("requireNonNull rejects = false");
        } catch (NullPointerException expected) {
            System.out.println("requireNonNull rejects = true");
        }
        try {
            Stream.of("group", (String) null)
                    .collect(Collectors.groupingBy(s -> s));
            System.out.println("grouping null key rejected = false");
        } catch (NullPointerException expected) {
            System.out.println("grouping null key rejected = true");
        }
        System.out.println("Objects.equals(null,null) = "
                + Objects.equals(null, null));
    }
}
~~~

Biên dịch với một JDK có hỗ trợ target Java 8:

~~~bash
javac --release 8 NullFilteringArithmeticDemo.java
java NullFilteringArithmeticDemo
~~~

Nếu dùng trực tiếp JDK 8, lệnh biên dịch là `javac NullFilteringArithmeticDemo.java`. Các APIs trong file có từ Java 8. Một JDK mới hơn có thể phát cảnh báo khi compiler target Java 8, nhưng đó không phải lỗi logic của các API.

**Stdout thực tế đã được xác minh:**

~~~text
isNull(null) = true
nonNull(null) = false
nonNull(0) = true
present = [0, 12, -3, 5]
missing count = 2
present count = 4
sum = 14
average = 3.5
positive sum = 17
all missing average present = false
unboxing null rejected = true
trimmed nonblank = [A, B]
nested present values = [10, 0, 7, -2]
nested sum = 15
group counts = {math=2, science=2}
sorted with nulls last = [-1, 0, 3, null, null]
decimal sum = 4.00
numeric finite sum = 4.0
one null is an element = 1
zero is kept = true
missing is not zero = true
valid port = 8080
requireNonNull rejects = true
grouping null key rejected = true
Objects.equals(null,null) = true
~~~

### 17.1. Vì sao nonNull(0) trả true?

`0` là giá trị primitive int, được autobox khi chuyển thành Object. Reference Integer không null. Một số zero là dữ liệu present, không phải missing.

### 17.2. Vì sao total=14 và average=3.5?

Sau khi bỏ hai null, các giá trị còn lại là `0,12,-3,5`. Tổng = 14, số mẫu = 4, average = 3.5. Nếu tất cả giá trị đều null, `average()` trả OptionalDouble empty, nên chương trình in `all missing average present = false`.

### 17.3. Vì sao không lọc thì unboxing bị lỗi?

`numbers` chứa null. Phép `Integer::intValue` trên null ném NullPointerException; code cố ý bắt để minh họa. Đây là đường failure đã được test, không phải behavior production khuyến nghị.

### 17.4. Vì sao nested sum=15 nhưng grouping bỏ một record?

Giá trị `7` thuộc `Reading(group=null,value=7)`, vẫn là số non-null nên tham gia tổng 10+0+7-2=15. Nhưng grouping có policy **bỏ group null**, nên chỉ đếm math=2 và science=2. Các thống kê được tính theo **hai điều kiện khác nhau**.

### 17.5. Vì sao decimal sum có dạng 4.00?

`BigDecimal` cộng các values có scale tương ứng: `1.20-0.20+3.00=4.00`, và `toPlainString()` giữ dạng thập phân. Điều này không nghĩa tất cả BigDecimal operations luôn tự chọn scale đúng cho mọi yêu cầu; division/rounding cần policy rõ.

### 17.6. Vì sao NaN/Infinity cần bộ lọc riêng?

`Objects::nonNull` chỉ loại null Double object. `Double::isFinite` loại NaN/Infinity, để lại 1.5 và 2.5, tổng 4.0. Null filtering không thay thế numeric validity.

### 17.7. Vì sao groupingBy null key bị từ chối?

`Collectors.groupingBy(s -> s)` nhận một phần tử null làm classifier result null, và JDK ném NPE. Filter trước hoặc đưa vào nhóm “unknown” có rule rõ ràng nếu cần giữ record.

### 17.8. Code demo không phải benchmark

Nó xác minh semantics của API và các ví dụ dữ liệu. Không dùng kết quả này để kết luận Stream nhanh hơn for-loop; muốn đo performance, dùng benchmark phù hợp với workload và lượng dữ liệu thực tế.

## 18. Ba mươi lỗi thường gặp và cách sửa

### Lỗi 1 — Xem null như số 0

Sai domain semantics. **Sửa:** phân biệt MISSING và số 0, không tự `orElse(0)` hay filter bỏ missing nếu chính sách không cho.

### Lỗi 2 — Xem Objects.nonNull(0) là false

Sai: autobox thành Integer non-null nên true. **Sửa:** muốn lọc zero, dùng numeric predicate `n -> n != 0` sau khi đã loại null.

### Lỗi 3 — Nghĩ Objects.nonNull kiểm tra String không rỗng

`""` cũng non-null. **Sửa:** filter null trước, rồi `String::trim` và `isEmpty` hoặc rule Unicode whitespace phù hợp.

### Lỗi 4 — Đặt mapToInt trước filter nonNull

Null wrapper bị unbox và NPE. **Sửa:** `filter(Objects::nonNull)` trước `mapToInt/mapToLong`.

### Lỗi 5 — Lọc object ngoài rồi tin nested field chắc non-null

`Reading` không null không chứng minh `Reading.value` có giá trị. **Sửa:** kiểm tra hoặc lọc nested field ở đúng tầng.

### Lỗi 6 — Chỉ lọc trước map mà map có thể trả null

Mapper có thể tạo null mới. **Sửa:** filter lại trước thao tác dereference kế tiếp.

### Lỗi 7 — Xem Objects.isNull là biến thể equals tổng quát

Nó chỉ kiểm tra null, không so sánh hai objects. **Sửa:** dùng `Objects.equals` khi mục tiêu là equality.

### Lỗi 8 — Nhầm nonNull với requireNonNull

`nonNull` trả boolean; `requireNonNull` throw nếu null. **Sửa:** chọn skip hay reject theo contract.

### Lỗi 9 — Nghĩ Stream.filter làm thay đổi collection nguồn

Không. **Sửa:** collect List mới hoặc dùng một mutation API nếu thực sự cần sửa nguồn.

### Lỗi 10 — Nghĩ Stream.of((String)null) rỗng

Nó có một phần tử null. **Sửa:** dùng `Stream.empty()` khi cần stream rỗng.

### Lỗi 11 — Gọi collection.stream trên collection null

NPE xảy ra trước filter. **Sửa:** validate collection reference ở boundary hoặc thiết kế source default rõ ràng.

### Lỗi 12 — Dùng Stream.of(null) mà không xem varargs overload

Có thể gây overload ambiguity/warning hoặc behavior không như ý. **Sửa:** cast `(String)null` khi cố ý tạo một phần tử null, hoặc tạo source rõ ràng.

### Lỗi 13 — Dùng findFirst/findAny trên stream có null mà không lọc

Có thể NPE nếu Optional phải chứa phần tử được chọn null. **Sửa:** filter nonNull trước terminal operation.

### Lỗi 14 — Gọi OptionalDouble.getAsDouble khi stream rỗng

Không có average. **Sửa:** kiểm tra `isPresent` hoặc trả OptionalDouble cho caller.

### Lỗi 15 — Coi average của missing là 0

Giá trị thống kê không xác định, không phải tự động zero. **Sửa:** giữ OptionalDouble/empty state.

### Lỗi 16 — Dùng mapToInt cho tổng rất lớn

`int` sum có thể overflow. **Sửa:** xem `mapToLong`, BigDecimal hay arithmetic policy theo miền số thực tế.

### Lỗi 17 — Nghĩ mapToLong loại mọi overflow

`long` cũng có giới hạn 64-bit. **Sửa:** nếu tổng có thể vượt long, dùng BigInteger/BigDecimal hoặc tính toán phát hiện overflow.

### Lỗi 18 — Dùng Objects::nonNull với IntStream.filter

`IntStream` không có null và predicate nhận int. **Sửa:** lọc wrapper stream trước unbox; primitive stream dùng numeric predicates.

### Lỗi 19 — Dùng nonNull để lọc NaN/Infinity

Chúng là Double references non-null. **Sửa:** thêm `Double::isFinite` nếu policy cần dữ liệu hữu hạn.

### Lỗi 20 — Dùng naturalOrder để sort List còn null

Comparator natural order không null-safe. **Sửa:** filter nonNull hoặc `Comparator.nullsFirst/nullsLast`.

### Lỗi 21 — Nhầm sort giữ null với filter xóa null

Hai operation có hậu quả khác nhau về số phần tử. **Sửa:** xác định cần giữ vị trí dữ liệu hay chỉ chọn sample present.

### Lỗi 22 — Dùng groupingBy khi classifier có thể trả null

JDK Java 8 ném NPE với classifier null key. **Sửa:** filter group nullable hoặc dùng mapping key sentinel có policy.

### Lỗi 23 — Tin groupingBy sẽ tự bỏ null ở value

Grouping không phải null filter của mọi nested field. **Sửa:** quyết định thống kê cần record count hay valid numeric count.

### Lỗi 24 — Dùng Collectors.toMap mà không quản lý duplicate/null

Duplicate keys có thể lỗi, null mapped values không được bảo đảm xử lý như mong đợi. **Sửa:** validate, filter và chọn merge function phù hợp.

### Lỗi 25 — Nghĩ Optional.of(null) cho empty

Nó ném NPE. **Sửa:** dùng `Optional.ofNullable` khi nullable hợp lệ.

### Lỗi 26 — Dùng String.isBlank trong project target Java 8

`String.isBlank` chỉ có ở Java mới hơn. **Sửa:** dùng logic tương thích Java 8 hoặc nâng target có chủ đích.

### Lỗi 27 — Dùng Stream.ofNullable trong `--release 8`

Method này là Java 9+. **Sửa:** dùng pipeline/filter hoặc idiom Java 8 phù hợp.

### Lỗi 28 — Xem dữ liệu CSV trống như null một cách tự động

Parser có thể trả empty String. **Sửa:** parse/normalize theo schema rồi phân biệt MISSING, INVALID, PRESENT.

### Lỗi 29 — Nhầm JDBC getInt 0 với SQL NULL

`getInt` có thể trả 0 khi SQL NULL, cần `wasNull()`. **Sửa:** dùng API truy vấn nullable và domain mapping phù hợp.

### Lỗi 30 — Bỏ missing trong tính tiền mà không báo

Một số giao dịch có amount null bị loại có thể làm tổng sai. **Sửa:** reject hoặc theo dõi đầy đủ số record missing theo business requirement.

### Lỗi 31 — Dùng Double sum cho tiền chính xác

Floating-point rounding có thể sai đơn vị nhỏ nhất. **Sửa:** BigDecimal với scale/rounding/validation phù hợp.

### Lỗi 32 — Mutate source collection trong filter

Can thiệp nguồn đang stream có thể gây lỗi/trạng thái không ổn định. **Sửa:** dùng pure predicates, trả collection mới.

### Lỗi 33 — Tin parallelStream tự làm source thread-safe

Nó không bảo vệ collection đang bị sửa đồng thời. **Sửa:** kiểm soát lifecycle nguồn hoặc dùng concurrent structure có semantics phù hợp.

### Lỗi 34 — Chạy nhiều terminal operations trên một Stream

Stream là single-use. **Sửa:** tạo stream mới từ nguồn hoặc dùng collector một lượt.

### Lỗi 35 — Xóa missing rồi mất dữ liệu audit

Có thể không biết bao nhiêu giá trị thiếu từng batch. **Sửa:** ghi lại total/missing/present counts hoặc kết quả phân loại có provenance.

## 19. Checklist khi thiết kế pipeline lọc dữ liệu

Trước khi dùng `Objects.nonNull`, trả lời:

1. Input stream có thể chứa **null elements** không?
2. Collection/source itself có thể null không?
3. Null nghĩa missing, invalid, not applicable hay không được phép?
4. Cần **bỏ**, **điền default**, **reject** hay **phân loại** null?
5. Có yêu cầu giữ số vị trí/timestamp alignment không?
6. Có phải ghi record count và missing count cho audit không?
7. Numeric zero là giá trị hợp lệ hay domain không cho phép?
8. Negative values có được chấp nhận không?
9. Dữ liệu là Integer/Long/Double/BigDecimal hay String số?
10. Có overflow risk khi sum với int hoặc long không?
11. Average tính trên present count hay all original count?
12. Empty data trả OptionalDouble hay 0 theo contract?
13. Field getter có thể trả null **sau** khi outer object đã được lọc không?
14. Các mapper có tạo null mới không?
15. `findFirst` hoặc `groupingBy` có được đặt sau null filter phù hợp chưa?
16. Group classifier có thể null không?
17. Null group có bị bỏ hay cần nhóm Unknown rõ ràng?
18. Cần sort loại null hay sắp null trước/cuối?
19. Với double, có NaN và infinities không?
20. Với tiền, có dùng BigDecimal và scale/rounding policy không?
21. Có dữ liệu CSV/JDBC/JSON phân biệt blank, omitted, null, zero không?
22. Source collection có bị mutate concurrent không?
23. Pipeline có stateless/non-interfering không?
24. Sử dụng target Java 8 hay Java mới hơn?
25. Code đã test trên các trường hợp missing/zero/negative/empty/nested null chưa?

### 19.1. Ma trận kiểm thử tối thiểu

| Case | Kỳ vọng |
| --- | --- |
| `Objects.isNull(null)` | true |
| `Objects.nonNull(null)` | false |
| `Objects.nonNull(0)` | true |
| `Objects.nonNull("")` | true |
| List chỉ có null | Present stream rỗng |
| List chỉ có null | Average empty, không tự zero |
| List có zero | Zero vẫn được giữ sau nonNull filter |
| List có số âm | Số âm vẫn được giữ nếu không có numeric predicate |
| List có null rồi unbox trực tiếp | NPE |
| Lọc null trước khi unbox | Không NPE do chính null element |
| Outer object null | Bị loại trước getter |
| Nested field null | Bị loại bằng một filter ở bước sau map |
| Classifier group null | Không truyền thẳng cho groupingBy |
| Sort có null | Sử dụng comparator null-safe |
| BigDecimal có null | Không gọi BigDecimal::add trên null nếu chưa xử lý |
| Double.NaN có object | nonNull true; filter isFinite nếu cần |
| Stream.of((String)null) | count=1 |
| Stream.empty() | count=0 |
| requireNonNull(null) | NPE |
| Optional.ofNullable(null) | Optional.empty |
| Input absent trong JSON | Không đồng nhất tự động với explicit null |
| JDBC getInt khi SQL NULL | Đọc `wasNull` đúng thời điểm |
| Parallel stream trên mutable source | Phải có contract concurrency riêng |

### 19.2. Bài tập unit test bổ sung

Có thể viết JUnit tests cho các pure transformations với danh sách đầu vào được thiết kế kiểm soát:

- All-missing, no-missing, mixed.
- Duplicate zero và negative numbers.
- Integer.MIN_VALUE/Integer.MAX_VALUE và sum overflow.
- Double.NaN, Infinity, -0.0.
- Null record và null nested amount/group.
- Grouping có null key trước/sau filter.
- Sorting với nullsFirst/nullsLast.
- Collections unmodifiable hoặc source streams chỉ một lượt.
- Result objects phải bảo tồn count + missing metadata nếu nghiệp vụ yêu cầu.

Kiểm thử phải xác nhận **hợp đồng nghiệp vụ**, không chỉ “pipeline không ném exception”.

## 20. Hỏi đáp tự kiểm tra

**Câu 1.** `Objects.nonNull` khác `Objects.isNull` như thế nào?

**Đáp án:** `nonNull` trả true nếu tham chiếu không null; `isNull` trả true nếu tham chiếu null. Chúng là hai kiểm tra đối nhau.

**Câu 2.** Vì sao `Objects.nonNull(0)` true?

**Đáp án:** Số nguyên 0 được autobox thành Integer reference non-null. Nó không phải kiểm tra numeric zero.

**Câu 3.** `Objects.nonNull("")` có true không?

**Đáp án:** Có. Empty String là object; muốn lọc blank cần predicate nội dung riêng.

**Câu 4.** `Stream.filter(Objects::nonNull)` có sửa List nguồn không?

**Đáp án:** Không. Filter tạo stream trung gian; source không bị xóa phần tử, trừ code khác sửa nguồn.

**Câu 5.** Vì sao phải filter trước `mapToInt(Integer::intValue)`?

**Đáp án:** Vì Integer null không thể unbox; nếu unbox trước sẽ NPE.

**Câu 6.** Stream có hai null và hai zero, sau nonNull filter còn bao nhiêu phần tử?

**Đáp án:** Hai zero; null bị bỏ, zero vẫn present.

**Câu 7.** Muốn đếm số missing, dùng gì?

**Đáp án:** `stream.filter(Objects::isNull).count()` hoặc `Collectors.partitioningBy` phù hợp.

**Câu 8.** Một String sau map có thể null dù input đã non-null không?

**Đáp án:** Có, getter hoặc mapper có thể trả null. Lọc lại ở đúng bước.

**Câu 9.** Có thể dùng `Objects::nonNull` trực tiếp với `IntStream.filter` không?

**Đáp án:** Không. IntStream chứa int primitives, không có null; IntPredicate kiểm tra numeric value.

**Câu 10.** `Stream.of((String)null)` có bao nhiêu phần tử?

**Đáp án:** Một phần tử null, count=1, khác Stream.empty.

**Câu 11.** `findFirst()` gặp phần tử được chọn là null thì sao?

**Đáp án:** Ném NullPointerException theo contract vì Optional không chứa null. Lọc trước.

**Câu 12.** `Collectors.groupingBy` có chấp nhận classifier trả null không?

**Đáp án:** Không trong Java 8: gây NullPointerException. Filter/group sentinel theo policy.

**Câu 13.** Vì sao `Objects.nonNull` không loại NaN?

**Đáp án:** NaN là một giá trị double/Double không null. Muốn finite numbers, thêm `Double::isFinite`.

**Câu 14.** Một tổng present bằng zero có chứng minh đã có mẫu không?

**Đáp án:** Không. Tổng các số có thể triệt tiêu hoặc stream rỗng cũng có sum zero. Cần theo dõi count.

**Câu 15.** `IntStream.average()` trả kiểu gì khi không có mẫu?

**Đáp án:** `OptionalDouble.empty()`, không phải zero mặc định.

**Câu 16.** Khi nào dùng `Objects.requireNonNull`?

**Đáp án:** Khi input/reference bắt buộc phải có và muốn fail fast; khác bỏ missing trong Stream.

**Câu 17.** Có nên bỏ null amounts trong hóa đơn không?

**Đáp án:** Không tự động; phải theo data contract, thường cần reject hoặc báo lỗi để không mất giao dịch.

**Câu 18.** Lọc nonNull rồi tính average có giữ số phần tử ban đầu không?

**Đáp án:** Không. Mẫu số là số phần tử còn lại, trừ khi ứng dụng có rule riêng.

**Câu 19.** `Comparator.nullsLast` khác nonNull filter ở đâu?

**Đáp án:** Nó giữ null và chỉ định thứ tự sắp xếp; filter xóa null khỏi stream kết quả.

**Câu 20.** `Objects.equals(null,null)` trả gì?

**Đáp án:** True, vì null-safe equality coi hai references null bằng nhau.

**Câu 21.** `Optional.ofNullable(null)` trả gì?

**Đáp án:** Optional.empty; khác Optional.of(null) ném NPE.

**Câu 22.** Java 8 có `Stream.ofNullable` và `String.isBlank` không?

**Đáp án:** Không. Đây là API Java mới hơn; với target Java 8 dùng patterns có sẵn tương ứng.

**Câu 23.** Nên chọn loop hay Stream để tính sum và count missing?

**Đáp án:** Chọn cách diễn đạt rõ, đúng và hiệu quả theo workload; vòng loop có thể tính hai số trong một traversal, Stream pipelines dễ ghép transformations. Đo nếu performance quan trọng.

**Câu 24.** `filter(Objects::nonNull)` có đảm bảo mọi input ngoài hệ thống đều hợp lệ không?

**Đáp án:** Không. Nó chỉ lọc null references; schema, numeric range, parse errors, NaN/Infinity và business validation là các bước riêng.

## 21. Tổng kết

- **`Objects.isNull(x)` kiểm tra null; `Objects.nonNull(x)` kiểm tra không null.** Đây là methods Java 8 vẫn dùng hiện nay; Javadoc thiết kế để làm predicates với `Stream.filter`.
- **Null không phải số 0**, không phải empty String và không phải NaN/Infinity. Cần xác định domain meaning trước khi bỏ, điền giá trị mặc định hoặc reject.
- **Lọc null trước khi unbox**: `stream.filter(Objects::nonNull).mapToLong(Integer::longValue)` tránh NPE do Integer null.
- **Lọc nhiều cấp khi dữ liệu lồng nhau**: object không null không bảo đảm field/ggetter không null; mapper có thể tạo null mới.
- **Không làm sai thống kê**: tổng và trung bình cần cùng sample policy; empty average là OptionalDouble.empty, không mặc định 0.
- **Terminal operations/collectors vẫn có rules riêng**: `findFirst` và `groupingBy` có trường hợp từ chối null; sorting dùng `Comparator.nullsFirst/nullsLast` nếu muốn giữ null.
- **Số học nâng cao vẫn cần kiểm soát**: int/long overflow, BigDecimal scale/rounding, Double.NaN/Infinity là các vấn đề khác null filtering.
- **`Objects.requireNonNull` để fail-fast input bắt buộc**, `Objects.nonNull` để chọn các phần tử present và `Objects.isNull` để đếm missing.
- **Stream pipelines nên stateless/non-interfering**, không tự làm mutable source thread-safe; performance cần đo theo workload.
- **Chương trình Java 8 đã biên dịch và chạy xác minh**, bao gồm tất cả các tình huống missing/zero/unboxing/nested/grouping/sorting/BigDecimal/finite double.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Objects](https://docs.oracle.com/javase/8/docs/api/java/util/Objects.html)
- [Oracle Java SE 26 — Objects, isNull và nonNull](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
- [Oracle Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html)
- [Oracle Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html)
- [Oracle Java SE 8 — IntStream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/IntStream.html)
- [Oracle Java SE 8 — Comparator](https://docs.oracle.com/javase/8/docs/api/java/util/Comparator.html)
- [Oracle Java SE 8 — Optional và OptionalDouble](https://docs.oracle.com/javase/8/docs/api/java/util/OptionalDouble.html)
- [Oracle Java SE 8 — BigDecimal](https://docs.oracle.com/javase/8/docs/api/java/math/BigDecimal.html)
- [Oracle Java SE 8 — Double.isFinite](https://docs.oracle.com/javase/8/docs/api/java/lang/Double.html)
- [Oracle Java SE 8 — ResultSet.wasNull](https://docs.oracle.com/javase/8/docs/api/java/sql/ResultSet.html)
