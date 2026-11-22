# ConcurrentHashMap.parallelismThreshold và lựa chọn xử lý song song trong Java

## 1. Mục tiêu bài học

`ConcurrentHashMap<K,V>` không chỉ là map hỗ trợ truy cập từ nhiều thread. Từ Java 8, lớp này còn cung cấp các **bulk operations** — `forEach`, `search` và `reduce` — có thể duyệt/xử lý nhiều phần tử tuần tự hoặc chia nhỏ thành tác vụ song song. Các biến thể nhận tham số đầu tiên kiểu `long` tên **`parallelismThreshold`**.

Mục đích của ngưỡng này là **cân bằng chi phí tạo và điều phối tác vụ** với lợi ích xử lý nhiều phần tử đồng thời. Đặt ngưỡng quá thấp cho map nhỏ có thể tốn overhead nhiều hơn công việc. Đặt ngưỡng quá cao có thể bỏ lỡ cơ hội tăng thông lượng khi mỗi phần tử cần tính toán đáng kể.

Sau bài này, bạn sẽ biết:

1. Chính xác `parallelismThreshold` có ý nghĩa gì, và **không phải** số lượng thread.
2. Khi nào dùng `1L`, `Long.MAX_VALUE` hoặc một ngưỡng trung gian.
3. Sử dụng đúng `forEach`, `search`, `reduce` cùng các biến thể `Keys`, `Values`, `Entries` và bộ chuyển đổi.
4. Vì sao hàm `reduce` phải **kết hợp (associative)** và **giao hoán (commutative)**; chọn `basis` trung hòa cho primitive reductions.
5. Vai trò của `null` trong `search`/`reduce` như tín hiệu “bỏ qua, không có kết quả”.
6. Cách thu kết quả **không phụ thuộc thứ tự traversal**, tránh race khi chạy callback song song.
7. Hiểu tính **weakly consistent** của bulk operations khi map đang bị thread khác cập nhật; không nhầm nó với một snapshot nguyên tử.
8. Quản lý chi phí common pool, workload CPU so với blocking I/O và hiệu ứng gây tranh chấp.
9. Thiết kế thử nghiệm benchmark công bằng, regression test và chọn chính sách song song dựa trên đo đạc.

`ConcurrentHashMap`, các bulk methods và tham số `parallelismThreshold` đều có từ **Java 8**, vẫn được hỗ trợ trong JDK hiện hành. Ví dụ chương trình dùng **Java 17+** để có `Map.copyOf`/`Stream.toList` và một số tiện ích chuẩn; API cốt lõi được học vẫn là `java.util.concurrent.ConcurrentHashMap`, không dựa vào kiến thức legacy.

## 2. `parallelismThreshold` là gì?

Định nghĩa thực hành của API: đây là **số lượng phần tử ước tính cần có để một bulk operation được xem xét thực thi song song**.

Những điểm quan trọng theo Javadoc:

- Nếu **kích thước map đang được ước tính nhỏ hơn threshold**, operation được thực hiện **tuần tự**.
- Đặt `parallelismThreshold = Long.MAX_VALUE` để **ngăn mọi parallelism** do bulk operation tạo ra.
- Đặt `parallelismThreshold = 1L` để **cho phép chia nhỏ tối đa**, nhằm khai thác `ForkJoinPool.commonPool()` mà triển khai dùng cho các tính toán song song.
- Giá trị trung gian có thể giảm lượng chia task khi chi phí overhead lớn. Cần **đo benchmark** để tìm ngưỡng hợp lý.
- Threshold **không phải** số lượng task chắc chắn được tạo, số CPU sẽ dùng, số thread bắt buộc chạy hay số phần tử mỗi chunk chính xác.
- `1L` **không bảo đảm** sẽ quan sát nhiều thread trong mọi môi trường; nếu map nhỏ, common pool thiếu tài nguyên, hoặc callback quá ngắn, speedup vẫn có thể bằng 0 hoặc âm.

Các đại lượng không đồng nhất:

| Đại lượng | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `map.mappingCount()` | Ước tính số mapping; `long` | Không phải snapshot nguyên tử khi có writer |
| `map.size()` | Số mapping kiểu `int`; dưới cập nhật đồng thời chỉ ước tính | Không phải đồng hồ tính concurrency |
| `parallelismThreshold` | Ngưỡng chọn cách chia nhỏ bulk operation | **Không phải thread count** |
| `ForkJoinPool.commonPool()` | Pool dùng cho tính toán song song của bulk operations | Không phải private executor do caller truyền vào |
| `forEach/search/reduce` | Các phép xử lý bulk trên map | Không mặc định có thứ tự và snapshot nguyên tử |

**Cách bắt đầu hợp lý:** với một workload chưa benchmark, thử **hai cực trị** `Long.MAX_VALUE` (thuần tuần tự) và `1L` (cho phép song song tối đa), sau đó đo các ngưỡng trung gian khi có bằng chứng cần thiết. Không có một giá trị threshold vạn năng cho mọi map, mọi CPU và mọi loại callback.

## 3. Hai cực trị: `Long.MAX_VALUE` và `1L`

Thử cùng một phép cộng trên map **không bị cập nhật** để quan sát rằng kết quả đúng **không thay đổi** khi chọn ngưỡng. Ví dụ dùng `reduceValuesToLong`, một phép reduction primitive kiểu `long`.

Lưu `CHMThresholdBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class CHMThresholdBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<Integer, Integer> map =
                new ConcurrentHashMap<>();
        map.put(1, 10);
        map.put(2, 20);
        map.put(3, 30);
        map.put(4, 40);

        long sequential = map.reduceValuesToLong(
                Long.MAX_VALUE,
                Integer::longValue,
                0L,
                Long::sum);

        long parallelEligible = map.reduceValuesToLong(
                1L,
                Integer::longValue,
                0L,
                Long::sum);

        LongAdder adder = new LongAdder();
        map.forEach(1L, (key, value) -> adder.add(value));

        System.out.println("mappingCount = " +
                map.mappingCount());
        System.out.println("sequential = " + sequential);
        System.out.println("parallelEligible = " +
                parallelEligible);
        System.out.println("forEachSum = " + adder.sum());
        System.out.println("sameResult = " +
                (sequential == parallelEligible));
    }
}
```

Chạy:

```bash
javac CHMThresholdBasicsDemo.java
java CHMThresholdBasicsDemo
```

Stdout:

```text
mappingCount = 4
sequential = 100
parallelEligible = 100
forEachSum = 100
sameResult = true
```

Đây **không phải** bài benchmark: hai phép tính trên chỉ có 4 phần tử và callback rất rẻ, nên `1L` có thể làm việc nặng hơn `Long.MAX_VALUE` vì chi phí chia nhỏ. Mục tiêu là hiểu **cùng nghiệp vụ, khác lựa chọn thực thi**.

### 3.1. Tại sao không kiểm tra số thread để khẳng định ngưỡng đúng?

JDK có thể xử lý một phần công việc trên thread gọi và nhiều phần trên common pool; số thread thật chịu ảnh hưởng bởi số CPU, kích thước/shape bảng băm, tình trạng pool và timing. Test kiểu `assert(threadNames.size() >= 2)` sẽ flaky trên CI nhỏ hoặc máy có common pool bận. Thay vào đó:

- **Correctness test:** assert kết quả, tính kết hợp/giao hoán của reducer và các bất biến.
- **Performance test:** đo throughput/latency dưới tải đại diện, không dùng kết quả chạy một lần như bằng chứng.
- **Diagnostic:** có thể log thread names khi gỡ lỗi, nhưng đừng đưa số thread quan sát được thành contract của `parallelismThreshold`.

## 4. Ba nhóm bulk operations

`ConcurrentHashMap` cung cấp ba họ chính:

**`forEach`:** đi qua các phần tử và thực hiện action. Có biến thể chỉ định transformer trước action; nếu transformer trả `null`, phần tử đó bị bỏ qua.

**`search`:** áp dụng search function lên các phần tử, trả một kết quả **khác null đầu tiên sẵn có**, hoặc `null` nếu không thấy. Khi tìm được, operation có thể **ngừng** xử lý thêm, nhưng trong thực thi song song vài callback khác vẫn có thể đang chạy. Không dựa vào “phần tử nhỏ nhất” hay “đầu tiên theo thứ tự insertion”.

**`reduce`:** gộp các kết quả bằng reducer. Hàm kết hợp cần **associative và commutative** vì thứ tự và cách nhóm các phần tử thay đổi. Có các phiên bản generic và các biến thể primitive `int`, `long`, `double` với `basis`.

Mỗi nhóm cung cấp dạng xử lý:

- `(key, value)` — ví dụ `map.forEach(threshold, (k,v) -> ...)`.
- `keys` — ví dụ `map.searchKeys(threshold, key -> ...)`.
- `values` — ví dụ `map.reduceValues(threshold, Integer::sum)`.
- `entries` — ví dụ `map.reduceEntries(threshold, (left,right) -> ...)`.

Đây là **bulk API của chính `ConcurrentHashMap`**. Đừng nhầm `map.forEach((k,v) -> ...)` của giao diện `Map` **không có tham số threshold** với `map.forEach(threshold,(k,v) -> ...)`. Cả hai đều hợp lệ nhưng là overload khác và có mục đích khác.

## 5. `forEach`: làm việc trên keys, values, entries và transformer

`forEach` thuận tiện cho công việc quan sát, thống kê, gửi tác vụ độc lập hoặc cập nhật các accumulator **thread-safe**. Nhưng thứ tự callback **không được bảo đảm**.

Bộ API đại diện:

```java
map.forEach(threshold, (key, value) -> action());
map.forEachKey(threshold, key -> action());
map.forEachValue(threshold, value -> action());
map.forEachEntry(threshold, entry -> action());
map.forEach(threshold, (key, value) -> transformOrNull,
            transformed -> action());
```

*Các dòng là cú pháp minh họa: `map`, `threshold`, `action()` và `transformOrNull` cần được khai báo. Chúng không phải một chương trình độc lập.*

Với biến thể có transformer, chỉ **kết quả khác null** mới được đưa tới action. Không thể cho phép giá trị `null` làm value trong `ConcurrentHashMap`, nhưng transformer **được phép** trả null để loại phần tử.

Lưu `CHMForEachVariantsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.atomic.LongAdder;

public class CHMForEachVariantsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("alpha", 1);
        map.put("beta", 2);
        map.put("gamma", 3);

        ConcurrentSkipListSet<String> keys =
                new ConcurrentSkipListSet<>();
        ConcurrentSkipListSet<String> entries =
                new ConcurrentSkipListSet<>();
        ConcurrentSkipListSet<String> filtered =
                new ConcurrentSkipListSet<>();
        LongAdder valuesSum = new LongAdder();

        map.forEachKey(1L, keys::add);
        map.forEachValue(1L, valuesSum::add);
        map.forEachEntry(1L, entry ->
                entries.add(entry.getKey() + ":" +
                            entry.getValue()));

        map.forEach(
                1L,
                (key, value) ->
                        value >= 2 ? key.toUpperCase() : null,
                filtered::add);

        System.out.println("keys = " + keys);
        System.out.println("valuesSum = " + valuesSum.sum());
        System.out.println("entries = " + entries);
        System.out.println("filtered = " + filtered);
    }
}
```

```bash
javac CHMForEachVariantsDemo.java
java CHMForEachVariantsDemo
```

```text
keys = [alpha, beta, gamma]
valuesSum = 6
entries = [alpha:1, beta:2, gamma:3]
filtered = [BETA, GAMMA]
```

Tại sao kết quả in luôn theo thứ tự chữ cái? Vì `ConcurrentSkipListSet` tự sắp xếp, **không phải** vì `ConcurrentHashMap.forEach` đã duyệt có thứ tự. Việc dùng tập concurrent bảo đảm thread-safe khi nhiều callback `forEach` cùng thêm phần tử.

**Không thay bằng `ArrayList` thường rồi `list.add(...)` từ callback song song.** `ArrayList` không thread-safe; có thể bị mất phần tử, hỏng dữ liệu hoặc có race condition. Với số lượng lớn, cũng cần cân nhắc chi phí contention của một collection đích dùng chung. Nếu chỉ cần tổng số, `LongAdder` phù hợp hơn một tập chứa toàn bộ phần tử.

### 5.1. Side effect trong `forEach` có được phép không?

Về chức năng, `forEach` được thiết kế để thực thi action, nên side effect có thể là mục tiêu. Tuy vậy side effect phải:

- **Thread-safe** nếu ngưỡng cho phép song song.
- Không dựa vào **thứ tự** callback.
- Không giả định toàn bộ map ở một trạng thái nhất quán duy nhất khi có writer.
- Không bắt buộc callback phải chạy đúng một số lần **nếu có concurrent modifications làm trạng thái thay đổi**.
- Có chính sách xử lý **partial work** nếu callback ném exception; không có rollback tự động.

Nếu action ghi dữ liệu ngoài hệ thống (email/payment), việc chạy song song có thể gây tác động khó bù trừ. Cần thiết kế idempotency, retry và ordering theo nghiệp vụ; `forEach` không cung cấp transaction/distributed exactly-once.

## 6. `search`: tìm kết quả khác null, nhưng không có thứ tự

`search` và các biến thể `searchKeys`, `searchValues`, `searchEntries` kết thúc với một kết quả **khác null sẵn có** do search function cung cấp. `null` có nghĩa “phần tử này chưa tạo kết quả”.

Thí dụ:

```java
String match = map.search(
        1L,
        (key, value) -> key.equals("bob")
                ? key + ":" + value
                : null);
```

*Snippet giả định `map` thuộc kiểu `ConcurrentHashMap<String,Integer>`.*

**Đừng dùng `search` để tìm “giá trị lớn nhất” khi có nhiều ứng viên.** Nếu nhiều callback trả non-null, kết quả nào được chọn có thể phụ thuộc cách chia task và lịch thực thi. Muốn lấy max/min, dùng **`reduce` với reducer giao hoán/kết hợp**, hoặc snapshot rồi sort theo quy tắc rõ ràng.

Lưu `CHMSearchVariantsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMSearchVariantsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> scores =
                new ConcurrentHashMap<>();
        scores.put("amy", 80);
        scores.put("bob", 95);
        scores.put("cat", 70);

        String byPair = scores.search(
                1L,
                (name, score) ->
                        name.equals("bob")
                                ? name + ":" + score
                                : null);
        String byKey = scores.searchKeys(
                1L, key -> key.equals("cat") ? key : null);
        String byValue = scores.searchValues(
                1L, value -> value == 70 ? "score70" : null);
        Integer byEntry = scores.searchEntries(
                1L, e -> e.getKey().equals("amy")
                        ? e.getValue() : null);
        String missing = scores.searchKeys(
                1L, key -> key.equals("nobody") ? key : null);

        System.out.println("pair = " + byPair);
        System.out.println("key = " + byKey);
        System.out.println("value = " + byValue);
        System.out.println("entry = " + byEntry);
        System.out.println("missing = " + missing);
    }
}
```

```bash
javac CHMSearchVariantsDemo.java
java CHMSearchVariantsDemo
```

```text
pair = bob:95
key = cat
value = score70
entry = 80
missing = null
```

Vì **mỗi lời gọi có đúng một phần tử thỏa điều kiện**, stdout không phụ thuộc thứ tự thread. Nếu đổi predicate thành `score >= 70` thì có ba ứng viên, không được cố định output là `amy` hay `bob`.

**Lưu ý về hủy công việc:** Search có thể bỏ qua các phần tử chưa xử lý khi đã tìm được một kết quả, nhưng không bảo đảm có thể hủy mọi callback đang chạy. Đừng thiết kế callback của search là thao tác side effect phải thực thi cho **mọi** phần tử.

## 7. `reduce`: kết hợp giá trị theo quy tắc đại số đúng

Khi các phần tử map **không có thứ tự**, chia nhỏ rồi gộp kết quả có thể tạo nhiều cây tính toán khác nhau. Vì vậy reducer phải:

- **Associative:** `combine(combine(a,b),c) == combine(a,combine(b,c))`.
- **Commutative:** `combine(a,b) == combine(b,a)`.

Ví dụ phù hợp với số nguyên không tràn theo hợp đồng:

- Cộng số nguyên: `Long::sum` (đối với `long` Java phép cộng modulo 2^64 vẫn có tính kết hợp/giao hoán về bit).
- Min/max: `Math::min`, `Math::max`.
- AND/OR bit, boolean conjunction/disjunction, các tập hợp gộp với quy tắc rõ ràng.

Ví dụ **không phù hợp** khi kết quả phải ổn định: phép trừ, nối chuỗi có thứ tự, ghép list theo traversal order, hoặc cập nhật một biến trạng thái mutable không đồng bộ. Với số thực floating point, phép cộng có thể thay đổi do sai số làm tròn khác nhau theo thứ tự gộp; cần xác định tolerance hoặc lựa chọn phép tính thích hợp.

Lưu `CHMReduceVariantsDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class CHMReduceVariantsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("a", 10);
        map.put("b", 20);
        map.put("c", 30);

        Integer sum = map.reduceValues(1L, Integer::sum);
        String maxKey = map.reduceKeys(
                1L,
                (a, b) -> a.compareTo(b) >= 0 ? a : b);

        Map.Entry<String, Integer> maxEntry =
                map.reduceEntries(
                        1L,
                        (a, b) -> a.getValue() >= b.getValue()
                                ? a : b);

        Long sumSelected = map.reduce(
                1L,
                (key, value) ->
                        value >= 20 ? Long.valueOf(value) : null,
                Long::sum);

        Integer filteredSum = map.reduceValues(
                1L,
                value -> value > 10 ? value : null,
                Integer::sum);

        ConcurrentHashMap<String, Integer> empty =
                new ConcurrentHashMap<>();

        System.out.println("sum = " + sum);
        System.out.println("maxKey = " + maxKey);
        System.out.println("maxEntry = " +
                maxEntry.getKey() + ":" +
                maxEntry.getValue());
        System.out.println("selected = " + sumSelected);
        System.out.println("filteredSum = " + filteredSum);
        System.out.println("emptyObject = " +
                empty.reduceValues(1L, Integer::sum));
        System.out.println("emptyPrimitive = " +
                empty.reduceValuesToLong(
                        1L, Integer::longValue, 0L, Long::sum));
    }
}
```

```bash
javac CHMReduceVariantsDemo.java
java CHMReduceVariantsDemo
```

```text
sum = 60
maxKey = c
maxEntry = c:30
selected = 50
filteredSum = 50
emptyObject = null
emptyPrimitive = 0
```

Ở đây value của `maxEntry` khác nhau, nên không có tie cần giải quyết. Nếu muốn lấy entry lớn nhất theo score khi **có hòa điểm**, phải định nghĩa thêm tie-break **deterministic**, ví dụ chọn key nhỏ nhất theo thứ tự chữ cái. Reducer như “trả operand bên trái nếu bằng điểm” không giao hoán cho hai entry khác nhau và có thể cho kết quả không ổn định.

`reduceEntries` nhận các `Map.Entry` tương ứng cặp key-value; đối tượng entry truyền vào bulk operations **không hỗ trợ `setValue`**. Không dùng reduction để sửa map thông qua entry. Muốn cập nhật value theo key, có các phương thức atomic như `compute`, `merge`, `replace`, nhưng những phương thức đó là một nhóm API **khác** với bulk reduction.

### 7.1. Null có ý nghĩa riêng trong object reductions

`ConcurrentHashMap` **không cho phép null key hoặc null value**. Trong `search` và `reduce` object:

- `null` do search function trả có nghĩa **chưa tìm thấy**.
- `null` do transformer trả có nghĩa **bỏ qua phần tử**.
- `null` là “basis ngầm” cho các reduction tham chiếu; nếu không có phần tử kết hợp nào, kết quả có thể là `null`.
- `null` **không** phải một value hợp lệ được map lưu mà reducer có thể trộn vào kết quả.

Trong `forEach` có transformer, action chỉ nhận những biến đổi **khác null**. Vì vậy cách viết `value >= 20 ? value : null` là bộ lọc tự nhiên khi cần gộp chỉ một nhóm giá trị.

## 8. Primitive reduction: chọn `basis` trung hòa

Đối với phiên bản primitive `reduceToLong`, `reduceValuesToInt`, `reduceKeysToDouble`... API nhận:

1. `parallelismThreshold`.
2. Transformer từ element sang primitive.
3. **`basis`** — phần tử trung hòa của phép gộp.
4. Reducer — hàm gộp primitive.

**Basis phải là identity element của reducer**, nghĩa là `reduce(basis, x) == x` và `reduce(x, basis) == x`. Quan trọng: khi tính song song, basis có thể được dùng cho **nhiều nhánh con**, không chỉ đúng một lần ở đầu toàn bộ phép tính. Vì vậy đừng coi basis là “giá trị khởi tạo để cộng thêm một lần”.

| Reducer | Basis đúng thường gặp | Sai phổ biến |
| --- | --- | --- |
| `Long::sum` | `0L` | `1L` làm sai tổng |
| `Math::max` cho `long` | `Long.MIN_VALUE` | `0L` làm sai khi mọi số đều âm |
| `Math::min` cho `long` | `Long.MAX_VALUE` | `0L` làm sai khi mọi số đều dương |
| Nhân số nguyên có kiểm soát overflow | `1L` | `0L` làm mọi kết quả bằng 0 |
| Boolean OR (nếu tự biểu diễn) | `false` | `true` |
| Boolean AND (nếu tự biểu diễn) | `true` | `false` |

Ví dụ dùng số âm để chứng minh chọn basis sai sẽ tạo kết quả không đúng.

Lưu `CHMIdentityBasisDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMIdentityBasisDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> numbers =
                new ConcurrentHashMap<>();
        numbers.put("a", -5);
        numbers.put("b", -2);
        numbers.put("c", -10);

        long sum = numbers.reduceValuesToLong(
                1L, Integer::longValue, 0L, Long::sum);
        long correctMax = numbers.reduceValuesToLong(
                1L, Integer::longValue,
                Long.MIN_VALUE, Math::max);
        long wrongMax = numbers.reduceValuesToLong(
                Long.MAX_VALUE, Integer::longValue,
                0L, Math::max);
        int intMax = numbers.reduceValuesToInt(
                1L, Integer::intValue,
                Integer.MIN_VALUE, Math::max);

        ConcurrentHashMap<String, Integer> empty =
                new ConcurrentHashMap<>();
        long emptyMax = empty.reduceValuesToLong(
                1L, Integer::longValue,
                Long.MIN_VALUE, Math::max);

        System.out.println("sum = " + sum);
        System.out.println("correctMax = " + correctMax);
        System.out.println("wrongMax = " + wrongMax);
        System.out.println("intMax = " + intMax);
        System.out.println("emptyMaxIsBasis = " +
                (emptyMax == Long.MIN_VALUE));
    }
}
```

```bash
javac CHMIdentityBasisDemo.java
java CHMIdentityBasisDemo
```

```text
sum = -17
correctMax = -2
wrongMax = 0
intMax = -2
emptyMaxIsBasis = true
```

**Vì sao sai ở `wrongMax`?** Nếu mọi element âm, 0 không phải identity của phép max; `max(0,-5)=0` nên kết quả sai ngay cả ở chế độ tuần tự. Việc giảm threshold không thể sửa một reducer hoặc basis đã sai về toán học.

Một primitive reduction trên map rỗng thường trả **basis**, chứ không trả null được vì kiểu primitive không mang null. Nếu ứng dụng cần phân biệt “map rỗng” với “kết quả thực sự bằng basis”, cần kiểm tra điều kiện riêng hoặc dùng dạng kết quả tham chiếu/Optional theo thiết kế.

### 8.1. Bẫy floating-point và overflow

Phép cộng số thực dạng `double` chỉ *xấp xỉ* tính kết hợp do IEEE-754 làm tròn. Một phép `reduceValuesToDouble(..., Double::sum)` có thể cho kết quả khác ở các mức bit khi thứ tự kết hợp thay đổi. Nếu yêu cầu tổng tiền chính xác, thường dùng số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` với chính sách phù hợp thay vì kỳ vọng số thực song song luôn cho kết quả bit-by-bit giống nhau.

Tổng `int`/`long` cũng cần xem xét overflow. Tính kết hợp theo số nguyên modulo không đồng nghĩa kết quả kinh doanh đúng khi vượt dải. Chọn kiểu/biểu diễn/kiểm tra overflow phù hợp; **không** dựa vào tăng parallelism để xử lý overflow.

## 9. Tính thống kê bằng `reduceValuesToLong`

Thống kê counters là ví dụ hữu ích cho `ConcurrentHashMap`, nhưng phải xác định map có đang được cập nhật không.

Giả sử map lưu số request đã xử lý ở từng nhóm:

```java
long total = map.reduceValuesToLong(
        threshold,
        value -> value.longValue(),
        0L,
        Long::sum);
```

*Snippet giả định map có values kiểu `Integer` hoặc tương đương; cần khai báo `threshold`.*

Nếu map đã ổn định trong lúc tính, tổng phản ánh các giá trị đã đọc. Nếu các thread khác tiếp tục update, không có **snapshot toàn map**; tổng có thể trộn giá trị ở những thời điểm khác nhau. Đó là tính chất của aggregate trên map đang biến động, không phải lỗi đặc thù của reduction.

Lưu `CHMStatisticsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMStatisticsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Long> latency =
                new ConcurrentHashMap<>();
        latency.put("api", 120L);
        latency.put("cache", 15L);
        latency.put("db", 65L);

        long total = latency.reduceValuesToLong(
                1L, Long::longValue, 0L, Long::sum);
        long max = latency.reduceValuesToLong(
                1L, Long::longValue, Long.MIN_VALUE, Math::max);
        long min = latency.reduceValuesToLong(
                1L, Long::longValue, Long.MAX_VALUE, Math::min);
        long count = latency.mappingCount();

        System.out.println("count = " + count);
        System.out.println("total = " + total);
        System.out.println("min = " + min);
        System.out.println("max = " + max);
        System.out.println("average = " + (total / count));
    }
}
```

```bash
javac CHMStatisticsDemo.java
java CHMStatisticsDemo
```

```text
count = 3
total = 200
min = 15
max = 120
average = 66
```

Phép chia `total / count` là **chia số nguyên**, ở đây làm tròn xuống `66`. Để lấy trung bình phần thập phân, ép sang `double` hoặc chọn cách tính số thập phân thích hợp. Với map có thể rỗng, kiểm tra `count > 0` trước khi chia, tránh chia 0.

**Quan trọng:** trong thực tế, lấy `mappingCount()` rồi reduction khi map đang được update không tạo một phép tính atomic. Nếu cần thống kê exact theo một epoch/batch, kiểm soát writers hoặc lưu các dữ liệu của epoch đó trong một snapshot nhất quán theo contract nghiệp vụ.

## 10. Chọn threshold theo cỡ map và độ nặng callback

Không nên áp dụng “cứ chạy song song là nhanh hơn”. Theo tài liệu Oracle, **chi phí chia task** có thể vượt quá chi phí công việc trên map nhỏ hoặc callback quá rẻ. Ngoài ra, common pool có thể đang xử lý tác vụ khác nên không có tài nguyên trống.

Một bảng chọn ban đầu:

| Tình huống | Lựa chọn thử trước | Vì sao |
| --- | --- | --- |
| Map nhỏ, action gần như chỉ cộng số | `Long.MAX_VALUE` | Tránh overhead tạo/chia task |
| Map lớn, mỗi phần tử có tính toán CPU rõ ràng, độc lập | `1L` rồi benchmark ngưỡng trung gian | Có khả năng phân phối công việc |
| Map lớn, callback rất rẻ | Benchmark cả hai cực trị | Overhead có thể vẫn thắng lợi ích |
| Callback có network/blocking I/O | Cân nhắc thiết kế khác, bounded executor/async client | Common pool không phải pool I/O tùy chỉnh |
| Callback cần thứ tự xác định | Không dùng thứ tự traversal song song | Chụp dữ liệu/sort và xử lý riêng |
| Callback thay đổi shared state không an toàn | Sửa code/data model trước | Threshold không làm side effect tự thread-safe |
| Map thay đổi liên tục, cần snapshot chính xác | Khóa/đồng bộ theo nghiệp vụ hoặc snapshot theo epoch | Bulk op không atomic toàn map |

**Heuristic minh họa, không phải con số production khuyến nghị:** có thể chọn threshold cao cho map vài phần tử và thử ngưỡng 1 cho map lớn. Con số “1.000 phần tử” dưới đây chỉ là **một nhánh quyết định ví dụ**; không có benchmark nào chứng minh 1.000 là mức tối ưu cho mọi hệ thống.

Lưu `CHMThresholdChoiceDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMThresholdChoiceDemo {
    private static long chooseThreshold(
            ConcurrentHashMap<Integer, Integer> map) {
        return map.mappingCount() < 1_000L
                ? Long.MAX_VALUE
                : 1L;
    }

    private static long total(
            ConcurrentHashMap<Integer, Integer> map,
            long threshold) {
        return map.reduceValuesToLong(
                threshold,
                Integer::longValue,
                0L,
                Long::sum);
    }

    public static void main(String[] args) {
        ConcurrentHashMap<Integer, Integer> small =
                new ConcurrentHashMap<>();
        for (int i = 1; i <= 4; i++) {
            small.put(i, i);
        }

        ConcurrentHashMap<Integer, Integer> large =
                new ConcurrentHashMap<>();
        for (int i = 1; i <= 2_000; i++) {
            large.put(i, i);
        }

        long smallThreshold = chooseThreshold(small);
        long largeThreshold = chooseThreshold(large);

        System.out.println("smallMode = " +
                (smallThreshold == Long.MAX_VALUE
                        ? "SEQUENTIAL" : "PARALLEL_ELIGIBLE"));
        System.out.println("largeMode = " +
                (largeThreshold == Long.MAX_VALUE
                        ? "SEQUENTIAL" : "PARALLEL_ELIGIBLE"));
        System.out.println("smallSum = " +
                total(small, smallThreshold));
        System.out.println("largeSum = " +
                total(large, largeThreshold));
    }
}
```

```bash
javac CHMThresholdChoiceDemo.java
java CHMThresholdChoiceDemo
```

```text
smallMode = SEQUENTIAL
largeMode = PARALLEL_ELIGIBLE
smallSum = 10
largeSum = 2001000
```

Tên `PARALLEL_ELIGIBLE` được dùng **có chủ đích**: threshold 1 khiến operation đủ điều kiện chia nhỏ, **không chứng minh** rằng nhiều CPU thực sự được sử dụng. Map không được cập nhật trong lúc reduction nên kết quả là cùng tổng số học.

### 10.1. Cách benchmark đúng khi chọn threshold

Một microbenchmark đáng tin cần:

1. Tạo **nhiều cỡ map** đại diện (nhỏ/vừa/lớn), phân bố keys và values gần dữ liệu thật.
2. Test cùng một phép tính với `Long.MAX_VALUE`, `1L` và một số threshold trung gian.
3. Có **warmup** để JIT tối ưu, nhiều iteration và đo bằng công cụ phù hợp như **JMH**.
4. Không đưa log I/O, `System.out.println` hay tạo executor/map trong phần thời gian đang đo nếu chúng không thuộc công việc cần benchmark.
5. Đo **latency, throughput, allocation, CPU utilization**, contention và ảnh hưởng lên các tác vụ khác dùng common pool.
6. Kiểm tra kết quả (correctness) ngoài đường đo performance.
7. Lặp lại trên **số core, container CPU quota, phiên bản JDK và tải production** đại diện.

**Không** khẳng định một con số “parallel nhanh gấp X lần” chỉ từ một lần chạy trên laptop. Hiệu quả song song phụ thuộc workload, kích cỡ map và cấu hình triển khai.

## 11. Cùng một map, nhiều writer: weak consistency chứ không phải snapshot

`ConcurrentHashMap` cho phép đọc/ghi đồng thời mà không ném `ConcurrentModificationException` như các collection fail-fast truyền thống. Các bulk operations của nó được thiết kế để **thích hợp với map đang được cập nhật**, nhưng:

- Không có bảo đảm **toàn map tại cùng một thời điểm**.
- Một mapping mới thêm có thể được nhìn thấy hoặc không thấy trong lượt duyệt.
- Một mapping bị xóa/cập nhật có thể đã được đọc ở trạng thái cũ hoặc mới, tùy thời điểm.
- `mappingCount` và `size` cũng chỉ nên xem là **ước tính** khi có cập nhật đồng thời.
- Chỉ ở trạng thái **quiescent** (không có writer trong lúc traversal) mới có thể lập luận như dữ liệu ổn định để kiểm tra kết quả exact.

Về memory visibility, các thao tác truy cập từng key có bảo đảm happens-before theo tài liệu, nhưng không có một **transactional snapshot** toàn bộ mapping. Sự tổng hợp các quan hệ trên từng phần tử không có nghĩa mọi phần tử được chụp cùng một timestamp.

### 11.1. Ví dụ tách “trạng thái đã đóng băng” khỏi map tiếp tục cập nhật

Trong một đoạn mã không có writer đồng thời, có thể lấy một bản sao độc lập rồi tiếp tục thay đổi map. Nhưng **`Map.copyOf(concurrentMap)` không tự trở thành một atomic snapshot nếu writer vẫn đang hoạt động**; ví dụ này cố ý tạo bản sao khi dữ liệu đã ổn định.

Lưu `CHMSnapshotBoundaryDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class CHMSnapshotBoundaryDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<Integer, Integer> live =
                new ConcurrentHashMap<>();
        live.put(1, 10);
        live.put(2, 20);

        // Snapshot được tạo khi không có writer đồng thời.
        Map<Integer, Integer> saved = Map.copyOf(live);

        live.put(2, 200);
        live.put(3, 30);

        long savedSum = saved.values().stream()
                .mapToLong(Integer::longValue)
                .sum();
        long liveSum = live.reduceValuesToLong(
                1L,
                Integer::longValue,
                0L,
                Long::sum);

        System.out.println("savedSize = " + saved.size());
        System.out.println("savedSum = " + savedSum);
        System.out.println("liveSize = " + live.size());
        System.out.println("liveSum = " + liveSum);
        System.out.println("savedSecond = " + saved.get(2));
        System.out.println("liveSecond = " + live.get(2));
    }
}
```

```bash
javac CHMSnapshotBoundaryDemo.java
java CHMSnapshotBoundaryDemo
```

```text
savedSize = 2
savedSum = 30
liveSize = 3
liveSum = 240
savedSecond = 20
liveSecond = 200
```

`Map.copyOf` có từ Java 10 và tạo map không thể sửa qua view của caller. Với values bất biến như `Integer`, bản sao giữ giá trị thời điểm copy; nếu value là một object mutable đang bị thread khác thay đổi, việc copy mapping **không deep-copy** object.

Nếu nghiệp vụ cần báo cáo nhất quán cùng một mốc, có thể áp dụng một trong các thiết kế: đóng một batch và không tiếp tục ghi lên map cũ, dùng version/epoch, khóa write ở tầng dữ liệu hoặc snapshot được tạo dưới cơ chế phối hợp rõ ràng. **`parallelismThreshold` không phải công cụ tạo snapshot.**

## 12. Accumulator thread-safe: `LongAdder` và atomic map updates

Khi nhiều thread tăng bộ đếm, `LongAdder` thường phù hợp với nhiều điểm contention. Có thể lưu `LongAdder` làm value trong `ConcurrentHashMap`, thêm key bằng `computeIfAbsent` rồi gọi `increment`.

Tuy nhiên, `LongAdder.sum()` **không phải snapshot nguyên tử** khi có cập nhật đồng thời. Nếu cần tổng exact cho một batch, đợi batch kết thúc hoặc dùng cơ chế nhất quán riêng.

Ví dụ sau tạo nhiều công việc cập nhật song song bằng executor, **đợi tất cả** kết thúc rồi mới gọi bulk reduction. `LongAdder` là accumulator thread-safe; phép đọc aggregate chỉ chạy khi không còn writer.

Lưu `CHMConcurrentUpdatesDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

public class CHMConcurrentUpdatesDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, LongAdder> counters =
                new ConcurrentHashMap<>();
        ExecutorService pool =
                Executors.newFixedThreadPool(4);

        try {
            CompletableFuture<?>[] writers =
                    IntStream.range(0, 300)
                    .mapToObj(i -> CompletableFuture.runAsync(
                            () -> counters.computeIfAbsent(
                                    "zone" + (i % 3),
                                    key -> new LongAdder())
                                    .increment(),
                            pool))
                    .toArray(CompletableFuture<?>[]::new);

            CompletableFuture.allOf(writers).join();

            long total = counters.reduceValuesToLong(
                    1L, LongAdder::sum, 0L, Long::sum);

            System.out.println("processed = 300");
            System.out.println("counted = " + total);
            System.out.println("zone0 = " +
                    counters.get("zone0").sum());
            System.out.println("zone1 = " +
                    counters.get("zone1").sum());
            System.out.println("zone2 = " +
                    counters.get("zone2").sum());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CHMConcurrentUpdatesDemo.java
java CHMConcurrentUpdatesDemo
```

```text
processed = 300
counted = 300
zone0 = 100
zone1 = 100
zone2 = 100
```

Trong ví dụ, cập nhật theo key được tạo/thực hiện qua `computeIfAbsent` và `LongAdder`. Không có mutation xảy ra khi reduction bắt đầu (vì barrier `allOf` đã hoàn tất), nên tổng xác định. Code không dùng `parallelismThreshold` để **tạo các tác vụ ghi**; nó chỉ dùng threshold để **đọc/reduce** các counter đã được ghi xong.

**Tránh nhầm:** `ConcurrentHashMap` bảo đảm thao tác map thread-safe, nhưng điều đó không làm cho một mutable value bên trong (ví dụ `ArrayList`, DTO có field thường) tự động thread-safe. Nếu value cần cập nhật đồng thời, hãy chọn value type, atomic operation hoặc bảo vệ riêng.

## 13. Thứ tự: bulk forEach không phải for-loop tuần tự có thứ tự

Dù cho `parallelismThreshold = Long.MAX_VALUE`, `ConcurrentHashMap` **không có contract bảo đảm thứ tự duyệt**. Đây không phải `LinkedHashMap` và không nên kỳ vọng duyệt theo thứ tự chèn key hoặc tăng dần.

Hai giải pháp hay dùng:

- **Không cần thứ tự:** giảm xuống một kết quả giao hoán/kết hợp, ví dụ sum/max.
- **Cần thứ tự trình bày:** thu an toàn vào tập/map concurrent hoặc tạo một snapshot phù hợp, sau đó **sort** theo comparator rõ ràng, cuối cùng in/serialize.

Lưu `CHMOrderSafetyDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentSkipListMap;

public class CHMOrderSafetyDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<Integer, String> source =
                new ConcurrentHashMap<>();
        source.put(3, "C");
        source.put(1, "A");
        source.put(2, "B");

        ConcurrentSkipListMap<Integer, String> ordered =
                new ConcurrentSkipListMap<>();

        source.forEach(1L, ordered::put);

        System.out.println("keys = " + ordered.keySet());
        System.out.println("values = " + ordered.values());
        System.out.println("size = " + ordered.size());
    }
}
```

```bash
javac CHMOrderSafetyDemo.java
java CHMOrderSafetyDemo
```

```text
keys = [1, 2, 3]
values = [A, B, C]
size = 3
```

**Đây không phải bằng chứng traversal đã theo thứ tự 1,2,3.** Thứ tự do `ConcurrentSkipListMap` giữ, còn bulk `forEach` có thể xử lý mapping theo bất cứ thứ tự nào.

Nếu hành động có side effect cần thứ tự toàn cục, ví dụ tạo các số thứ tự nghiệp vụ, không nên cố dựng bằng callback song song trên map; hãy sort rồi áp dụng một pipeline có order/cơ chế sequence rõ ràng.

## 14. Exceptions và hậu quả khi đang chạy song song

Các callback transformer/reducer/action có thể ném exception. Theo tài liệu:

- Bulk operation có thể **kết thúc bất thường** do exception từ một callback.
- Khi làm song song, callback khác có thể đã chạy, đang chạy hoặc cũng đã ném exception.
- Không có bảo đảm exception đầu tiên hiển thị là **mọi lỗi** đã xảy ra.
- Side effects đã thực hiện không tự rollback.

Điều cần test là **loại hành vi** (có lỗi, có chính sách partial work), không phải “chính xác mấy callback đã chạy trước khi lỗi”.

Lưu `CHMExceptionDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMExceptionDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<Integer, Integer> map =
                new ConcurrentHashMap<>();
        map.put(1, 10);
        map.put(2, 20);
        map.put(3, 30);

        boolean errorObserved = false;
        try {
            map.forEach(1L, (key, value) -> {
                if (key == 2) {
                    throw new IllegalStateException("bad item");
                }
            });
        } catch (RuntimeException ex) {
            errorObserved = true;
        }

        System.out.println("errorObserved = " +
                errorObserved);
        System.out.println("mapSize = " + map.size());
        System.out.println("untouchedValue = " + map.get(2));
    }
}
```

```bash
javac CHMExceptionDemo.java
java CHMExceptionDemo
```

```text
errorObserved = true
mapSize = 3
untouchedValue = 20
```

Map không bị thay đổi vì callback chỉ ném lỗi, không sửa map. Nhưng điều này **không** có nghĩa bulk operation cung cấp transaction; nếu callback đã ghi dữ liệu ngoài, phải có cơ chế bù trừ/rollback riêng.

**Tối ưu lỗi:** nếu muốn báo tất cả item thất bại, không nên dùng một bulk `forEach` đơn lẻ rồi trông chờ exception ngoài cùng mang đầy đủ danh sách. Hãy thiết kế xử lý và thu outcomes thread-safe theo key/id, hoặc phân chia batch với cơ chế retry đã được định nghĩa.

## 15. So sánh với `parallelStream` và stream tuần tự

Vì `ConcurrentHashMap` cung cấp `keySet`, `values` và `entrySet`, bạn cũng có thể viết stream:

```java
long total = map.values().parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
```

*Snippet giả định `map` là `ConcurrentHashMap<?,Integer>`.*

Cần phân biệt:

| Cách tiếp cận | Cấu hình song song | Điểm mạnh | Lưu ý |
| --- | --- | --- | --- |
| `map.reduceValuesToLong(threshold, ...)` | Threshold của bulk operation | Gọn cho map bulk, được thiết kế cho concurrent maps | Chọn identity/reducer phù hợp |
| `map.forEach(threshold,...)` | Threshold | Duyệt map, action có thể chạy song song | Không có thứ tự, side effects cần an toàn |
| `map.values().stream()` | Tuần tự ở pipeline stream | Diễn đạt pipeline mapping/filtering quen thuộc | Không phải snapshot nếu map đang thay đổi |
| `map.values().parallelStream()` | Stream parallel flag | Dễ biến đổi pipeline stream | Cũng có overhead, không nhận cùng tham số threshold |
| Copy/sort rồi stream | Điều khiển source/order | Hữu ích nếu cần thứ tự hoặc dataset bất biến | Copy trong lúc có writer không tự atomic |

`parallelStream` và bulk parallelism không hoán đổi hoàn toàn: chúng có API, chính sách splitting và hình dạng pipeline khác nhau. Cả hai có thể dùng tài nguyên common pool theo các cơ chế triển khai tương ứng. Đừng giả định đổi sang parallelStream chắc chắn nhanh hơn hoặc có snapshot nhất quán hơn.

Lưu `CHMStreamComparisonDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMStreamComparisonDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<Integer, Integer> map =
                new ConcurrentHashMap<>();
        for (int i = 1; i <= 100; i++) {
            map.put(i, i);
        }

        long sequentialStream = map.values().stream()
                .mapToLong(Integer::longValue)
                .sum();

        long parallelStream = map.values().parallelStream()
                .mapToLong(Integer::longValue)
                .sum();

        long bulkSequential = map.reduceValuesToLong(
                Long.MAX_VALUE,
                Integer::longValue,
                0L,
                Long::sum);

        long bulkParallel = map.reduceValuesToLong(
                1L,
                Integer::longValue,
                0L,
                Long::sum);

        System.out.println("stream = " + sequentialStream);
        System.out.println("parallelStream = " +
                parallelStream);
        System.out.println("bulkSequential = " +
                bulkSequential);
        System.out.println("bulkParallel = " + bulkParallel);
        System.out.println("allEqual = " +
                (sequentialStream == parallelStream
                 && parallelStream == bulkSequential
                 && bulkSequential == bulkParallel));
    }
}
```

```bash
javac CHMStreamComparisonDemo.java
java CHMStreamComparisonDemo
```

```text
stream = 5050
parallelStream = 5050
bulkSequential = 5050
bulkParallel = 5050
allEqual = true
```

Kết quả bằng nhau vì map đứng yên và phép cộng đủ đơn giản, hợp lệ. **Không** kết luận bốn cách có latency tương đương: đây là bài kiểm tra correctness, không đo tốc độ.

## 16. Map rỗng, null và lọc phần tử

Với `ConcurrentHashMap`:

- `put(null, value)` và `put(key, null)` **không hợp lệ**, ném `NullPointerException`.
- `reduceValues(threshold, reducer)` trả `null` nếu không có giá trị để gộp.
- `reduceValuesToLong(threshold, transformer, basis, reducer)` trả `basis` nếu không có phần tử, vì primitive không có null.
- `search(threshold, function)` trả `null` nếu không tìm thấy kết quả non-null.
- `forEach` với transformer trả null cho phần tử không quan tâm ⇒ action không được gọi cho phần tử đó.
- Tất cả tham số function/action cho task bulk phải khác null.
- Nếu một operation đang chạy đồng thời với writer, đừng dùng kết quả null như bằng chứng về trạng thái **ổn định ở mọi thời điểm**; đó là kết quả trong traversal tương ứng.

Lưu `CHMEmptyAndNullDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class CHMEmptyAndNullDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        System.out.println("emptySearch = " +
                map.search(1L, (k, v) -> k));
        System.out.println("emptyReduce = " +
                map.reduceValues(1L, Integer::sum));
        System.out.println("emptyPrimitive = " +
                map.reduceValuesToLong(
                        1L, Integer::longValue,
                        0L, Long::sum));

        boolean nullRejected = false;
        try {
            map.put("x", null);
        } catch (NullPointerException ex) {
            nullRejected = true;
        }

        map.put("one", 1);
        map.put("two", 2);
        map.put("three", 3);

        LongAdder count = new LongAdder();
        map.forEach(
                1L,
                (key, value) ->
                        value >= 2 ? key : null,
                ignored -> count.increment());

        System.out.println("nullRejected = " +
                nullRejected);
        System.out.println("filteredCount = " +
                count.sum());
    }
}
```

```bash
javac CHMEmptyAndNullDemo.java
java CHMEmptyAndNullDemo
```

```text
emptySearch = null
emptyReduce = null
emptyPrimitive = 0
nullRejected = true
filteredCount = 2
```

`null` trong transformer ở đây là **dấu hiệu không có kết quả**, không phải value nằm trong map. Nếu value thực sự có thể “không tồn tại” trong domain, cân nhắc đặt một object sentinel/Optional trong value hoặc cấu trúc dữ liệu thích hợp, nhưng không cố ghi `null` trực tiếp vào `ConcurrentHashMap`.

## 17. Common pool: tài nguyên chia sẻ, không phải executor tùy biến qua threshold

Javadoc ghi rõ bulk parallel computations sử dụng `ForkJoinPool.commonPool()`. Lập trình viên **không truyền một custom ExecutorService vào `forEach(threshold,...)` hoặc `reduce...(threshold,...)`** như một tham số của các bulk API này.

Các hậu quả:

- Common pool thường được chia sẻ với các thành phần khác của JVM. Một bulk operation chạy dài có thể cạnh tranh CPU với phần việc khác.
- Có thể có CPU limit trong container; “parallel” không bảo đảm chạy trên nhiều core thực sự.
- Callback **blocking I/O** có thể giữ worker bận và làm giảm thông lượng; phải cân nhắc executor/client async phù hợp cho I/O, thay vì dựa vào bulk operation.
- Khi callback quá ngắn, chi phí chia task và phối hợp có thể lớn hơn công việc.
- Điều chỉnh threshold không thay đổi đồng thời mức max connection, giới hạn rate API hay chi phí database.
- Ngoài threshold, hiệu năng còn phụ thuộc phân bố key trong các bin, số mapping và số lượng CPU thực sự sẵn có.

**Không** dùng threshold như “số thread chính xác 8” hay “mỗi task xử lý 100 entries” — đó không phải contract API.

### 17.1. Có nên đưa bulk operation vào một custom ForkJoinPool?

Đừng phụ thuộc vào chi tiết triển khai về thread nơi task được fork để suy ra một cơ chế **được bảo đảm** ép bulk method dùng pool riêng. Hợp đồng chính thức của bulk operations nêu common pool cho parallel computations, không cung cấp tham số executor. Nếu yêu cầu cô lập thread pool và kiểm soát tải I/O thật sự, hãy thiết kế pipeline task riêng có `ExecutorService`/`CompletableFuture` hoặc batch engine của ứng dụng.

## 18. Correctness trước performance: những bất biến cần test

Một số test ổn định cần có:

1. **Cùng kết quả** giữa `Long.MAX_VALUE` và `1L` khi map quiescent và reducer hợp lệ.
2. **Không phụ thuộc thứ tự** khi dùng `search` (chỉ một match) và `reduce` (associative/commutative).
3. **Null lọc phần tử** trong transformer nhưng map vẫn không chứa null key/value.
4. **Map rỗng** cho kết quả null/basis tương ứng.
5. **Basis đúng** với mọi số âm hoặc mọi số dương.
6. **Nhiều reader/writer** nhưng không đưa assertion exact trên map đang thay đổi nếu không có cơ chế nhất quán.
7. **Accumulator thread-safe** và kết quả sau khi writers kết thúc.
8. **Callback lỗi** có thể làm operation throw; không khẳng định thứ tự callback/partial work.
9. **Thứ tự output** nếu cần chỉ lấy từ sort/sequence rõ ràng.
10. **Hiệu năng** được đo riêng, không suy ra tốc độ từ correctness.

Không viết unit test dựa vào `Thread.sleep` để ép một luồng đọc thấy một mapping mới. Dùng barrier như `CountDownLatch`/`CompletableFuture` nếu cần xác minh thời điểm bắt đầu/kết thúc theo một hợp đồng đã định nghĩa; với weak consistency, chỉ assert những bảo đảm API thực sự cung cấp.

### 18.1. Lời giải thực hành đầy đủ

**Bài 1:** Tạo map chứa bốn số và tính tổng hai lần với threshold cực trị; kiểm tra bằng nhau.

**Bài 2:** Chọn key lớn nhất theo thứ tự chữ cái bằng `reduceKeys` và giá trị lớn nhất bằng `reduceValues`. Vì sao hai kết quả không phụ thuộc thứ tự callback?

**Bài 3:** Dùng `reduce(1L, transformer, reducer)` để tổng hợp chỉ các giá trị từ 20 trở lên; transformer trả null cho giá trị không hợp lệ.

**Bài 4:** Một map chỉ chứa số âm. Vì sao `reduceValuesToLong(..., 0L, Math::max)` sai? Basis nào đúng?

**Bài 5:** Chọn threshold cho map 50 phần tử, callback cực rẻ, và map 100.000 phần tử với phép tính CPU nặng. Chọn hai cực trị để thử nghiệm rồi thiết kế benchmark JMH. Không được tuyên bố trước kết quả đo.

**Bài 6:** Một writer đang thêm mapping khi reader gọi reduce. Có thể đảm bảo tổng chính xác là trạng thái map tại instant bắt đầu hay kết thúc không? Đề xuất snapshot/epoch policy nếu nghiệp vụ yêu cầu exact.

Lưu `CHMParallelThresholdPractice.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class CHMParallelThresholdPractice {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("a", 10);
        map.put("b", 20);
        map.put("c", 30);
        map.put("d", 40);

        long sequentialSum = map.reduceValuesToLong(
                Long.MAX_VALUE,
                Integer::longValue,
                0L,
                Long::sum);

        long parallelSum = map.reduceValuesToLong(
                1L,
                Integer::longValue,
                0L,
                Long::sum);

        String greatestKey = map.reduceKeys(
                1L, (a, b) -> a.compareTo(b) >= 0 ? a : b);

        Long filtered = map.reduce(
                1L,
                (key, value) ->
                        value >= 20 ? Long.valueOf(value) : null,
                Long::sum);

        System.out.println("sequential = " + sequentialSum);
        System.out.println("parallel = " + parallelSum);
        System.out.println("sameSum = " +
                (sequentialSum == parallelSum));
        System.out.println("greatestKey = " + greatestKey);
        System.out.println("filtered = " + filtered);
    }
}
```

```bash
javac CHMParallelThresholdPractice.java
java CHMParallelThresholdPractice
```

```text
sequential = 100
parallel = 100
sameSum = true
greatestKey = d
filtered = 90
```

Đáp án trọng tâm bài 4 là `Long.MIN_VALUE` cho phép `Math::max` trên số `long` âm; bài 5 yêu cầu benchmark, không dự đoán speedup; bài 6 cần định nghĩa **thời điểm đóng dữ liệu** hoặc cơ chế phối hợp writers để có dữ liệu nhất quán.

## 19. Checklist trước khi dùng trong production

- Tôi thực sự cần bulk `forEach/search/reduce` hay chỉ muốn `get`/`compute` cho một key?
- `parallelismThreshold` tôi chọn là **ngưỡng**, không phải số thread/chunk?
- Đã thử `Long.MAX_VALUE` và `1L` rồi đo hiệu năng trên workload đại diện chưa?
- Map nhỏ hoặc callback cực nhẹ có tránh song song hóa quá mức không?
- Map lớn/callback CPU nặng có đủ tài nguyên để tận dụng parallelism không?
- Có nhận thức rằng common pool có thể bị các tác vụ JVM khác sử dụng không?
- Callback có blocking I/O hoặc giữ connection lâu không? Đã cô lập bằng thiết kế phù hợp?
- Nếu dùng reducer, nó có **kết hợp và giao hoán** không?
- Với primitive reducer, `basis` có thực sự là identity không?
- `null` trong transformer dùng như bộ lọc, không bị nhầm với value hợp lệ?
- Với `search`, có tránh kỳ vọng “match đầu tiên theo key/insertion order” không?
- Side effects trong `forEach` có thread-safe và không phụ thuộc thứ tự không?
- Có tránh dùng `ArrayList`/`HashMap` thường như output shared giữa nhiều callback?
- Có xử lý callback throw và biết partial effects không tự rollback?
- Map đang được cập nhật có được xem là **weakly consistent** thay vì snapshot atomic?
- Nếu báo cáo yêu cầu số liệu exact, đã đóng batch/epoch hoặc có cơ chế snapshot phù hợp chưa?
- Khi dùng `LongAdder` làm value, có đợi writer kết thúc trước khi lấy tổng exact không?
- Nếu cần thứ tự output, đã sort với comparator rõ ràng thay vì in trực tiếp từ callback?
- Test correctness có tránh khẳng định số thread/timing/throughput cố định không?
- Các ví dụ Java đang dùng API hiện hành, không lẫn `Map.forEach` với overload bulk có threshold?

## 20. Tài liệu chính thức và kết luận

Tài liệu Oracle Java SE 26:

- `ConcurrentHashMap` — tổng quan bulk operations, `parallelismThreshold`, forEach/search/reduce và identity: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- `ForkJoinPool` — common pool và cơ chế chia task: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- `LongAdder` — accumulator có khả năng mở rộng khi contention: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `ConcurrentSkipListMap` — map đồng thời duy trì thứ tự: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html
- `ConcurrentSkipListSet` — tập đồng thời có thứ tự: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html
- `Map` — contract chung và các view: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html

**Tổng kết:** `parallelismThreshold` trả lời “map cần lớn đến mức nào để cân nhắc chia bulk operation thành việc song song?”, **không** trả lời “chạy bao nhiêu thread”. `Long.MAX_VALUE` tắt parallelism; `1L` cho phép chia tối đa theo common pool, nhưng hiệu năng tùy chi phí công việc và môi trường. Độ đúng trước hết phụ thuộc reducer associative/commutative, basis trung hòa, xử lý null đúng quy tắc, callback thread-safe và việc không coi bulk operation là snapshot nguyên tử. Hãy **đo workload thật** rồi mới chọn ngưỡng trung gian.