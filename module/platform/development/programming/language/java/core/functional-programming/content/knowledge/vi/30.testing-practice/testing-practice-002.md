# Kiểm tra nguồn rỗng, một phần tử, null và dữ liệu trùng trong Java Stream

## 1. Vì sao phải kiểm thử các trường hợp biên?

Một pipeline Stream có thể cho kết quả đúng với dữ liệu mẫu nhiều phần tử nhưng vẫn sai khi:

- **Nguồn rỗng:** không có phần tử nào để `map`, `filter`, `reduce` hay `collect` xử lý.
- **Nguồn chỉ có một phần tử:** các phép tìm kiếm, nhóm, chia đôi hoặc lấy phần tử đầu/cuối không được dựa vào giả định có ít nhất hai phần tử.
- **Giá trị `null`:** có thể là chính **tham chiếu nguồn bằng null**, hoặc chỉ **một phần tử trong nguồn bằng null**; hai tình huống phải xử lý khác nhau.
- **Dữ liệu trùng lặp:** `distinct`, `groupingBy`, `toMap` và nghiệp vụ đếm/tổng hợp có ý nghĩa khác nhau khi nhiều bản ghi trùng khóa.

Trong Java, Stream là **một pipeline xử lý dữ liệu**, không phải bảo đảm rằng dữ liệu luôn hợp lệ hoặc không bao giờ thiếu. Test tốt cần xác định **hợp đồng mong muốn** của từng tình huống trước khi viết phép biến đổi.

Ví dụ:

```java
List<String> names = List.of();
List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
System.out.println(result); // []
```

Pipeline hợp lệ và trả danh sách rỗng. Nhưng dòng sau có thể lỗi:

```java
String first = names.stream()
        .findFirst()
        .orElseThrow(); // NoSuchElementException.
```

Sự khác biệt nằm ở **terminal operation và chính sách xử lý vắng mặt**, không phải bản thân dữ liệu rỗng luôn là lỗi.

**Mục tiêu bài học:** xây một bộ kiểm thử có thể chạy lại cho bốn nhóm tình huống này, nắm rõ semantics của Stream API Java 17 và biết lựa chọn cách xử lý đúng thay vì che giấu dữ liệu bất thường.

## 2. Ma trận test tối thiểu

Đầu tiên, hãy viết rõ input và expected output:

| Ca thử | Nguồn | Pipeline | Kết quả mong đợi |
| --- | --- | --- | --- |
| Rỗng | `[]` | `filter(...).toList()` | `[]` |
| Rỗng | `[]` | `count()` | `0` |
| Rỗng | `[]` | `findFirst()` | `Optional.empty()` |
| Một phần tử | `["solo"]` | `map(toUpperCase).toList()` | `["SOLO"]` |
| Một phần tử | `["solo"]` | `count()` | `1` |
| Có null | `["A", null, "B"]` | `toList()` | Giữ phần tử null |
| Có null | `["A", null, "B"]` | `filter(nonNull).toList()` | `["A","B"]` |
| Có null | `["A", null, "B"]` | `map(String::trim)` | `NullPointerException` khi gặp null |
| Trùng | `["a","b","a"]` | `distinct().toList()` | `["a","b"]` với stream ordered |
| Trùng khóa | `["x","x"]` | `toMap` không merge | `IllegalStateException` |
| Trùng khóa | `["x","x"]` | `toMap` có merge đếm | `{x=2}` |
| Null classifier | `[null]` | `groupingBy(identity)` | `NullPointerException` |
| Nguồn tùy chỉnh | `Iterable` rỗng hoặc trùng | `StreamSupport.stream` | Tương ứng danh sách rỗng hoặc kết quả đã khử trùng |

Đây là **bộ ca cơ sở**, không phải danh sách cố định áp dụng máy móc. Tùy bài toán, phải thêm dữ liệu không hợp lệ, nhiều kích thước, dữ liệu rất lớn, thứ tự khác nhau, tràn số, lỗi I/O, cạnh tranh luồng và ranh giới thời gian.

**Nguyên tắc:** test khẳng định **kết quả hoặc loại lỗi theo hợp đồng**, không assert chi tiết implementation như tên class nội bộ của `Stream.toList()` hay thứ tự xử lý ngẫu nhiên của parallel stream.

## 3. Nguồn rỗng: nhiều operation có giá trị hoàn toàn hợp lệ

Với `Stream.empty()` hoặc `List.of().stream()`:

```java
List<Integer> empty = List.of();

System.out.println(empty.stream().toList()); // []
System.out.println(empty.stream().count());  // 0
System.out.println(empty.stream().filter(n -> n > 0).toList()); // []
```

`filter`, `map` và `flatMap` không có phần tử nào cần xử lý, nên kết quả thu thập vẫn rỗng. Điều này khác với trường hợp **nguồn không tồn tại** (biến `List` bằng null), phân tích ở phần sau.

### `findFirst`, `min`, `max` và `average` dùng Optional

```java
boolean none = Stream.<String>empty()
        .findFirst()
        .isEmpty();

boolean noMax = java.util.stream.IntStream.empty()
        .max()
        .isEmpty();

boolean noAverage = java.util.stream.IntStream.empty()
        .average()
        .isEmpty();

System.out.println(none);      // true
System.out.println(noMax);     // true
System.out.println(noAverage); // true
```

`findFirst` trả `Optional<T>`, `IntStream.max` trả `OptionalInt`, `IntStream.average` trả `OptionalDouble`. Với nguồn rỗng, không có phần tử đầu tiên, số lớn nhất hay trung bình.

Không gọi `get()`/`getAsInt()`/`getAsDouble()` vô điều kiện trên Optional rỗng. Có thể dùng `orElse` hoặc `orElseThrow` tùy nghiệp vụ:

```java
String display = Stream.<String>empty()
        .findFirst()
        .orElse("NO_DATA");

System.out.println(display); // NO_DATA
```

Nếu “không có dữ liệu” là trạng thái bình thường, dùng fallback rõ ràng; nếu đó là lỗi nghiệp vụ, ném exception được định nghĩa bởi ứng dụng.

### Các phép toán đối sánh trên Stream rỗng

`anyMatch`, `allMatch`, `noneMatch` có logic đáng kiểm thử:

```java
boolean any = Stream.<Integer>empty()
        .anyMatch(n -> n > 0);  // false

boolean all = Stream.<Integer>empty()
        .allMatch(n -> n > 0);  // true

boolean none = Stream.<Integer>empty()
        .noneMatch(n -> n > 0); // true
```

`allMatch` trả `true` với tập rỗng theo quy tắc **đúng một cách hiển nhiên (*vacuous truth*)**: không có phần tử nào vi phạm điều kiện. `noneMatch` cũng đúng vì không có phần tử thỏa; `anyMatch` sai vì không tìm thấy phần tử nào thỏa.

Nếu hệ thống định nghĩa “tất cả đơn hàng đạt chuẩn” chỉ có nghĩa khi có ít nhất một đơn, hãy thêm điều kiện kiểm tra không rỗng ở cấp nghiệp vụ, thay vì thay đổi suy luận hợp đồng của `allMatch`.

### `reduce`: có identity hay không có identity

```java
int zero = Stream.<Integer>empty()
        .reduce(0, Integer::sum); // 0

boolean absent = Stream.<Integer>empty()
        .reduce(Integer::sum)
        .isEmpty(); // true
```

Overload `reduce(identity, accumulator)` trả **identity** với nguồn rỗng, còn `reduce(accumulator)` không có identity trả `Optional.empty()`. Dùng identity đúng với phép toán: với cộng là 0, nhân là 1, nhưng không có “mặc định đúng” cho mọi bài toán domain.

### Đừng dựa vào side effect trong pipeline rỗng

Nếu một mapper, predicate hoặc `peek` không được gọi vì không có phần tử, đó là hành vi tự nhiên. Nhưng **đừng biến số lần gọi mapper/peek thành cơ chế audit**: một số terminal như `count` có thể được tối ưu theo kích thước nguồn, không bắt buộc chạy toàn bộ intermediate operation chỉ để đếm.

## 4. Một phần tử: phép biến đổi và xác thực ranh giới

Nguồn có đúng một phần tử là bài test giúp phát hiện code tự giả định có phần tử thứ hai:

```java
List<String> single = List.of("solo");

System.out.println(single.stream().count()); // 1
System.out.println(single.stream()
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .toList()); // [SOLO]
System.out.println(single.stream()
        .findFirst().orElseThrow()); // solo
```

`findFirst` ở đây có giá trị nên `orElseThrow` trả `solo`; nó khác với nguồn rỗng ở phần 3.

Những tình huống đáng thêm test:

- `limit(0)` trên một phần tử phải tạo stream rỗng; `limit(1)` giữ một phần tử.
- `skip(1)` trên một phần tử tạo stream rỗng.
- `distinct` trên một phần tử giữ một phần tử.
- `sorted` trên một phần tử không cần đổi thứ tự.
- `min`/`max` trên một phần tử trả chính giá trị ấy.
- `collect(groupingBy(...))` tạo một nhóm nếu classifier cho một khóa hợp lệ.

`Stream` không có `get(index)`. Nếu muốn truy cập phần tử tại vị trí, cần cân nhắc dùng List, `skip`/`findFirst`, hoặc mô hình dữ liệu phù hợp; không viết logic ngầm kỳ vọng stream có truy cập ngẫu nhiên.

### Không nhầm “một phần tử” với “một phần tử null”

`Stream.of((String) null)` tạo một stream **có một phần tử, và phần tử đó là null**. Nó khác `Stream.empty()`, và khác `Stream.ofNullable((String) null)` vốn trả stream rỗng:

```java
System.out.println(Stream.of((String) null).count()); // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
```

Việc ép `(String) null` làm ví dụ không mơ hồ với overload varargs của `Stream.of`. Nhưng gọi `findFirst()` trên một stream có phần tử đầu tiên null có thể ném `NullPointerException` vì `Optional` không thể chứa giá trị null hiện diện. Hãy kiểm tra contract của nguồn trước khi dùng terminal trả Optional.

## 5. Ba khái niệm null khác nhau

Một số lỗi kiểm thử bắt nguồn từ việc dùng cùng từ “null” cho ba tình huống:

| Tình huống | Ví dụ | Hành vi |
| --- | --- | --- |
| **Nguồn là null** | `List<String> list = null; list.stream()` | Ném `NullPointerException` khi gọi trên tham chiếu null |
| **Nguồn hợp lệ chứa phần tử null** | `Arrays.asList("A", null, "B")` | Nguồn vẫn có ba phần tử; mapper có thể lỗi khi gặp null |
| **Một giá trị tùy chọn là null** | `Stream.ofNullable(null)` | Tạo stream rỗng |
| **Optional tham chiếu bằng null** | `Optional<String> opt = null; opt.stream()` | Ném `NullPointerException`; API sử dụng sai hợp đồng |

Cách xử lý phải phù hợp chính sách nghiệp vụ:

- Nếu nguồn **bắt buộc tồn tại**, dùng `Objects.requireNonNull(source)` để báo lỗi sớm, rõ vị trí.
- Nếu nguồn **được phép vắng mặt**, chuyển thành collection rỗng hoặc dùng phương án xử lý Optional, nhưng phải nói rõ điều đó trong contract.
- Nếu **phần tử null hợp lệ**, quyết định giữ, loại bỏ, thay bằng sentinel hay báo lỗi.
- Nếu null biểu thị **dữ liệu hỏng**, không được tự âm thầm bỏ qua chỉ vì pipeline có thể lọc nó.

Đừng mặc định rằng mọi null đều giống nhau hoặc mọi null đều phải biến thành chuỗi `"UNKNOWN"`.

### `List.of` không cho phần tử null

```java
// Ví dụ cố ý gây NullPointerException:
List<String> invalid = List.of((String) null);
```

`List.of` (Java 9+) từ chối null khi tạo danh sách. Trong chương trình chạy, cần bắt exception hoặc test bằng `assertThrows`; không viết đoạn này trước các test khác rồi để chương trình dừng ngoài ý muốn.

Một collection có thể chứa null để kiểm thử:

```java
List<String> nullable = java.util.Arrays.asList("A", null, "B");
```

`Arrays.asList` là danh sách kích thước cố định và có thể chứa null trong ví dụ. Nó **không phải** là một `ArrayList` mutable hoàn toàn theo kích thước, và việc thay phần tử bằng `set` có contract khác với `Stream.toList`.

## 6. Xử lý null trong pipeline

Giả sử:

```java
List<String> values = java.util.Arrays.asList(" A ", null, "B");
```

### Cách 1 — Giữ null như dữ liệu

```java
List<String> retained = values.stream().toList();
System.out.println(retained); // [ A , null, B]
```

`Stream.toList()` (Java 16+) tạo list unmodifiable nhưng **cho phép chứa null**. Điều này không có nghĩa mọi collector và mọi phương thức List của JDK cũng cho phép null.

### Cách 2 — Bỏ null nếu được phép

```java
List<String> nonNull = values.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::trim)
        .toList();

System.out.println(nonNull); // [A, B]
```

`filter(Objects::nonNull)` đứng **trước** `map(String::trim)` nên tránh gọi instance method trên null. Nếu đảo thứ tự, có thể ném `NullPointerException` trước khi tới bước lọc.

### Cách 3 — Thay null bằng một giá trị domain xác định

```java
List<String> shown = values.stream()
        .map(value -> value == null ? "MISSING" : value.trim())
        .toList();

System.out.println(shown); // [A, MISSING, B]
```

Phương án này chỉ đúng khi `"MISSING"` là một biểu diễn hợp lệ và không nhầm với giá trị thực. Khi cần phân biệt nhiều nguyên nhân lỗi, dùng một model trạng thái rõ ràng thay vì một chuỗi đặc biệt.

### Cách 4 — `Stream.ofNullable` và `flatMap`

`Stream.ofNullable(T)` trả stream một phần tử nếu T không null, ngược lại trả stream rỗng. Từ Java 9:

```java
List<String> clean = values.stream()
        .flatMap(Stream::ofNullable)
        .map(String::trim)
        .toList();

System.out.println(clean); // [A, B]
```

Về kết quả đơn giản này, nó tương đương lọc bằng `Objects::nonNull`. Chọn cách diễn đạt trực quan và nhất quán với codebase. `Stream.ofNullable` cũng hữu ích khi một phép biến đổi có thể trả null và bạn muốn chuyển mỗi kết quả thành **0 hoặc 1 phần tử**.

### Cách 5 — Cho null ở cuối khi sắp xếp

`sorted()` mặc định dựa trên thứ tự tự nhiên; nguồn có null có thể ném `NullPointerException` nếu comparator hoặc phép so sánh phải xử lý null. Nếu nghiệp vụ **cho phép null** và muốn xếp nó sau giá trị thật:

```java
List<String> sorted = values.stream()
        .sorted(java.util.Comparator.nullsLast(
                java.util.Comparator.naturalOrder()))
        .toList();

System.out.println(sorted); // [ A , B, null]
```

Ở đây chuỗi `" A "` có khoảng trắng đầu/cuối nên thứ tự tự nhiên được tính trên giá trị gốc; không tự trim. Nếu muốn sắp xếp trên dữ liệu đã chuẩn hóa, hãy chuẩn hóa trước rồi sắp xếp.

## 7. Null ở `groupingBy` và `toMap`

Không phải collector nào cũng chấp nhận khóa null.

`Collectors.groupingBy(classifier)` yêu cầu classifier cho khóa **khác null**. Nếu classifier trả null, việc thu thập ném `NullPointerException`:

```java
// Cố ý lỗi: classifier trả null cho phần tử null.
Map<String, List<String>> groups = Stream.of((String) null)
        .collect(java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity()));
```

Ví dụ này phải được dùng trong test mong đợi exception, không phải happy-path.

Nếu “không có giá trị” là một nhóm có ý nghĩa, tạo khóa sentinel **không null**:

```java
Map<String, List<String>> groups = values.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                s -> s == null ? "MISSING" : s.trim()));
```

Ví dụ này **không quyết định** rằng danh sách bên trong phải bỏ null: một nhóm `"MISSING"` vẫn có thể chứa chính phần tử gốc null. Nếu downstream hoặc serializer không cho phép null, hãy ánh xạ/phòng vệ tương ứng.

Với `Collectors.toMap`, hai phần tử có cùng key làm collector **không có merge function** ném `IllegalStateException`. Đây là lỗi do **khóa trùng**, không nhất thiết do null. Cách sửa là định nghĩa hợp đồng giữ trước/giữ sau/cộng dồn:

```java
Map<String, Integer> counts = Stream.of("x", "x", "y")
        .collect(java.util.stream.Collectors.toMap(
                java.util.function.Function.identity(),
                value -> 1,
                Integer::sum));

System.out.println(counts.get("x")); // 2
```

Không nên chọn một merge function chỉ để hết exception nếu nghiệp vụ thực sự cấm hai bản ghi cùng mã. Khi trùng là dấu hiệu dữ liệu sai, để fail-fast với thông báo đủ rõ hoặc validate duplicates trước khi ghi hệ thống.

## 8. Kiểm tra dữ liệu trùng: `distinct` sử dụng `equals`

`distinct()` là intermediate operation loại các phần tử trùng lặp theo `Object.equals`:

```java
List<String> unique = Stream.of("a", "b", "a", "c", "b")
        .distinct()
        .toList();

System.out.println(unique); // [a, b, c]
```

Với stream có encounter order, `distinct` giữ **phần tử đầu tiên** của mỗi nhóm giá trị bằng nhau theo `equals`. Trong parallel stream **có thứ tự**, ổn định theo encounter order vẫn là một phần của contract, dù có chi phí phối hợp lớn hơn.

### Trùng về ký tự khác trùng về ý nghĩa

`"Java"` và `"java"` là hai chuỗi **không bằng nhau theo `String.equals`**. Nếu nghiệp vụ coi chúng giống nhau, hãy chuẩn hóa trước:

```java
List<String> words = List.of(" Java ", "java", "JAVA", "Stream");

List<String> unique = words.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .toList();

System.out.println(unique); // [java, stream]
```

Đặt `distinct` trước chuẩn hóa sẽ không loại đúng các bản ghi trùng về ý nghĩa. Thứ tự các bước **chuẩn hóa → distinct** là một quyết định dữ liệu cụ thể, nên có test khẳng định.

### Record và khóa nghiệp vụ không nhất thiết giống nhau

`record Order(String id, int amount)` có `equals` dựa trên **các component**. Do vậy:

```java
record Order(String id, int amount) {}

List<Order> orders = List.of(
        new Order("A", 10),
        new Order("A", 10),
        new Order("A", 20)
);

System.out.println(orders.stream().distinct().count()); // 2
System.out.println(orders.stream()
        .map(Order::id).distinct().count());             // 1
```

Đây là đoạn **minh họa** phải đặt trong một lớp/phương thức Java hợp lệ. Hai bản ghi `("A",10)` trùng hoàn toàn theo record equality, còn `("A",20)` có amount khác nên **không trùng object-value**. Nhưng nếu kiểm tra **trùng ID**, cả ba cùng có ID A. Đừng giả định `distinct` trên object tự biết khóa nghiệp vụ là trường nào.

Khi cần phát hiện bản ghi trùng ID với nội dung khác, `groupingBy(Order::id)` hoặc `toMap` với chính sách merge/validate phù hợp thường rõ hơn.

## 9. Đếm tần suất thay vì loại bỏ bản sao

`distinct` làm mất thông tin **có bao nhiêu bản ghi trùng**. Nếu mục tiêu là báo cáo số lần xuất hiện, dùng `groupingBy(..., counting())`:

```java
List<String> raw = List.of(
        " Alpha ", "alpha", "BETA", "beta", "alpha");

Map<String, Long> counts = raw.stream()
        .map(String::trim)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .collect(java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity(),
                java.util.TreeMap::new,
                java.util.stream.Collectors.counting()));

System.out.println(counts); // {alpha=3, beta=2}
```

Dùng `TreeMap::new` giúp **thứ tự khóa khi in xác định** theo comparator tự nhiên. `groupingBy` mặc định không hứa kiểu map hoặc thứ tự iteration cụ thể; nếu viết expected stdout theo `map.toString()`, hãy chủ động chọn một map có thứ tự hoặc so sánh từng entry.

### Lấy key trùng với số lần xuất hiện lớn hơn 1

```java
List<String> duplicates = counts.entrySet().stream()
        .filter(entry -> entry.getValue() > 1L)
        .map(Map.Entry::getKey)
        .toList();

System.out.println(duplicates); // [alpha, beta]
```

Trong đoạn này `counts` là `TreeMap` nên stream trên `entrySet` có encounter order theo khóa; output xác định. Nếu dùng `HashMap`, đừng ràng buộc thứ tự duyệt các khóa mà không có `sorted`.

## 10. Chương trình Java 17 hoàn chỉnh: self-test không cần JUnit

Ví dụ này tạo một **bộ assertion nhỏ** để kiểm tra dữ liệu rỗng, singleton, null, trùng lặp, lỗi collector, thứ tự kết quả và nguồn `Iterable` tùy chỉnh. Chương trình **ném `AssertionError` ngay khi một hợp đồng không đúng**, vì vậy dòng cuối `All checks passed` chỉ xuất hiện khi mọi phép kiểm tra đã thành công.

Tạo file **`StreamEdgeCasesDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class StreamEdgeCasesDemo {
    record Order(String id, int amount) {}

    static void expectEqual(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    static void expectThrows(Class<? extends Throwable> type,
                             Runnable action,
                             String label) {
        boolean matched = false;
        try {
            action.run();
        } catch (Throwable ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError(label
                        + " unexpected exception: " + ex, ex);
            }
            matched = true;
        }
        if (!matched) {
            throw new AssertionError(label
                    + " expected " + type.getSimpleName());
        }
    }

    public static void main(String[] args) {
        // 1. Nguồn rỗng.
        List<String> empty = List.of();
        List<String> emptyResult = empty.stream()
                .map(String::toUpperCase)
                .toList();
        expectEqual(List.of(), emptyResult, "empty toList");
        expectEqual(0L, empty.stream().count(), "empty count");
        expectEqual(true, empty.stream().findFirst().isEmpty(),
                "empty findFirst");
        expectEqual(false, Stream.<Integer>empty()
                .anyMatch(n -> n > 0), "empty anyMatch");
        expectEqual(true, Stream.<Integer>empty()
                .allMatch(n -> n > 0), "empty allMatch");
        expectEqual(true, Stream.<Integer>empty()
                .noneMatch(n -> n > 0), "empty noneMatch");
        System.out.println("Empty: " + emptyResult);
        System.out.println("Empty count: " + empty.stream().count());
        System.out.println("Empty first present: "
                + empty.stream().findFirst().isPresent());
        System.out.println("Empty any/all/none: false/true/true");

        // 2. Nguồn một phần tử.
        List<String> singleton = List.of("solo");
        List<String> singleUpper = singleton.stream()
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();
        expectEqual(List.of("SOLO"), singleUpper, "singleton map");
        expectEqual("solo", singleton.stream()
                .findFirst().orElseThrow(), "singleton first");
        expectEqual(1L, singleton.stream().count(), "singleton count");
        System.out.println("Singleton: " + singleUpper);

        // 3. Nguồn hợp lệ có phần tử null.
        List<String> nullable = Arrays.asList("A", null, "B");
        List<String> keptNull = nullable.stream().toList();
        List<String> removedNull = nullable.stream()
                .filter(Objects::nonNull)
                .toList();
        List<String> substituted = nullable.stream()
                .map(s -> s == null ? "MISSING" : s)
                .toList();
        List<String> usingNullable = nullable.stream()
                .flatMap(Stream::ofNullable)
                .toList();
        List<String> sortedNullLast = nullable.stream()
                .sorted(Comparator.nullsLast(
                        Comparator.naturalOrder()))
                .toList();

        expectEqual(Arrays.asList("A", null, "B"),
                keptNull, "toList keeps null");
        expectEqual(List.of("A", "B"), removedNull,
                "filter nonNull");
        expectEqual(List.of("A", "MISSING", "B"),
                substituted, "substitute null");
        expectEqual(List.of("A", "B"), usingNullable,
                "flatMap ofNullable");
        expectEqual(Arrays.asList("A", "B", null),
                sortedNullLast, "nullsLast");
        expectEqual(0L, Stream.ofNullable((String) null).count(),
                "ofNullable null is empty");

        System.out.println("Nullable retained: " + keptNull);
        System.out.println("Nullable filtered: " + removedNull);
        System.out.println("Nullable substituted: " + substituted);
        System.out.println("Nullable flatMap: " + usingNullable);
        System.out.println("Nullable sorted: " + sortedNullLast);

        // 4. Những lỗi cần assert chứ không bỏ qua.
        expectThrows(NullPointerException.class,
                () -> List.of((String) null),
                "List.of(null)");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null)
                        .map(String::trim).toList(),
                "method call on null");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null).findFirst(),
                "findFirst of null");
        expectThrows(NullPointerException.class,
                () -> nullable.stream()
                        .collect(Collectors.toUnmodifiableList()),
                "toUnmodifiableList of null");
        expectThrows(NullPointerException.class,
                () -> Stream.of((String) null)
                        .collect(Collectors.groupingBy(
                                Function.identity())),
                "groupingBy null key");
        expectThrows(UnsupportedOperationException.class,
                () -> keptNull.add("C"),
                "Stream.toList is unmodifiable");
        System.out.println("Null error cases: checked");

        // 5. Chuẩn hóa và khử trùng.
        List<String> raw = List.of(
                " Alpha ", "alpha", "BETA", "beta", "alpha");
        List<String> normalized = raw.stream()
                .map(String::trim)
                .map(s -> s.toLowerCase(Locale.ROOT))
                .toList();
        List<String> distinctTokens = normalized.stream()
                .distinct()
                .toList();
        Map<String, Long> frequency = normalized.stream()
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        TreeMap::new,
                        Collectors.counting()));

        expectEqual(List.of("alpha", "beta"),
                distinctTokens, "distinct tokens");
        expectEqual(Map.of("alpha", 3L, "beta", 2L),
                frequency, "frequency");
        System.out.println("Distinct tokens: " + distinctTokens);
        System.out.println("Frequency: " + frequency);

        // 6. Dùng record equality khác với khóa nghiệp vụ.
        List<Order> orders = List.of(
                new Order("A", 10),
                new Order("A", 10),
                new Order("A", 20),
                new Order("B", 10));
        List<Order> distinctRecords = orders.stream()
                .distinct()
                .toList();
        List<String> distinctIds = orders.stream()
                .map(Order::id)
                .distinct()
                .toList();

        expectEqual(3, distinctRecords.size(), "record equality");
        expectEqual(List.of("A", "B"),
                distinctIds, "business key");
        System.out.println("Unique records: " + distinctRecords.size());
        System.out.println("Distinct IDs: " + distinctIds);

        // 7. toMap cần chính sách với khóa trùng.
        expectThrows(IllegalStateException.class,
                () -> Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                Function.identity(),
                                String::length)),
                "duplicate key without merge");

        Map<String, Integer> merged = Stream.of("x", "x", "y")
                .collect(Collectors.toMap(
                        Function.identity(),
                        value -> 1,
                        Integer::sum,
                        TreeMap::new));
        expectEqual(Map.of("x", 2, "y", 1),
                merged, "duplicate count merge");
        System.out.println("Duplicate key merged: " + merged);

        // 8. distinct của stream ordered giữ lần xuất hiện đầu.
        List<String> parallelDistinct =
                List.of("a", "b", "a", "c")
                        .parallelStream()
                        .distinct()
                        .toList();
        expectEqual(List.of("a", "b", "c"),
                parallelDistinct, "ordered parallel distinct");
        System.out.println("Parallel distinct: " + parallelDistinct);

        // 9. Nguồn Iterable tùy chỉnh (không cần Collection.stream).
        Iterable<String> custom =
                () -> Arrays.asList("old", "old", null).iterator();
        List<String> customUnique = StreamSupport
                .stream(custom.spliterator(), false)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        expectEqual(List.of("old"), customUnique, "custom Iterable");
        System.out.println("Custom source: " + customUnique);

        System.out.println("All checks passed");
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 StreamEdgeCasesDemo.java
java StreamEdgeCasesDemo
```

**Stdout dự kiến xác định:**

```text
Empty: []
Empty count: 0
Empty first present: false
Empty any/all/none: false/true/true
Singleton: [SOLO]
Nullable retained: [A, null, B]
Nullable filtered: [A, B]
Nullable substituted: [A, MISSING, B]
Nullable flatMap: [A, B]
Nullable sorted: [A, B, null]
Null error cases: checked
Distinct tokens: [alpha, beta]
Frequency: {alpha=3, beta=2}
Unique records: 3
Distinct IDs: [A, B]
Duplicate key merged: {x=2, y=1}
Parallel distinct: [a, b, c]
Custom source: [old]
All checks passed
```

### Tại sao stdout này ổn định?

1. `empty` và `singleton` là `List` có encounter order rõ. Các phép toán thu thập đều tạo kết quả tương ứng với số phần tử đầu vào.
2. `Arrays.asList("A", null, "B")` có null ở giữa. `toList` giữ null, `filter` và `flatMap(Stream::ofNullable)` loại null theo chủ đích, còn `Comparator.nullsLast` đưa null về cuối.
3. Các trường hợp ném exception được **bắt trong `expectThrows`**. Chỉ khi exception có kiểu đúng mới tiếp tục đến dòng `Null error cases: checked`.
4. Chuẩn hóa bằng `trim` và `toLowerCase(Locale.ROOT)` cho lần lượt alpha, alpha, beta, beta, alpha. `distinct` giữ lần xuất hiện đầu alpha/beta; `TreeMap` in các khóa theo thứ tự alpha rồi beta.
5. Với record `Order`, hai bản ghi A/10 bằng nhau; A/20 khác; B/10 khác. Do đó `distinctRecords.size()` là 3. Nhưng sau khi chỉ lấy `id`, giá trị khác nhau là A và B.
6. `toMap` có merge function `Integer::sum` biến hai lần x thành count=2, y thành 1. `TreeMap` bảo đảm thứ tự hiển thị key.
7. `parallelStream().distinct().toList()` trên nguồn `List` ordered bảo toàn tính ổn định của `distinct`; kết quả là a,b,c bất kể lịch chạy các thread. Không có side effect nào phụ thuộc thứ tự thread trong ví dụ.
8. `custom` cho ba phần tử old, old, null. Sau khi lọc null và loại trùng, chỉ còn old. Không cần dựa vào thứ tự của một nguồn unordered vì sau xử lý chỉ còn một giá trị.
9. Dòng `All checks passed` chỉ xuất hiện sau khi toàn bộ expected values và expected exceptions đã được xác minh. Nếu một assertion sai, chương trình dừng bằng `AssertionError`.

**Không nhầm “stdout không đổi” với “đã kiểm thử mọi tình huống song song”.** Bộ ví dụ tập trung vào kết quả dữ liệu theo contract. Với nguồn/custom Spliterator có trạng thái, vẫn cần test race, tài nguyên và độ chính xác việc chia dữ liệu.

## 11. Kiểm thử ngoại lệ: phải phát hiện đúng loại lỗi

Một test có giá trị phải xác định **điều được phép xảy ra**. Các kiểu lỗi phổ biến:

| Tình huống | Loại exception đáng mong đợi |
| --- | --- |
| `List.of((String)null)` | `NullPointerException` |
| Gọi `String::trim` trên phần tử null | `NullPointerException` |
| `Optional.empty().get()` | `NoSuchElementException` |
| `findFirst` chọn phần tử null | `NullPointerException` |
| `Collectors.groupingBy` nhận null classifier key | `NullPointerException` |
| `Collectors.toMap` gặp khóa trùng, không có merge | `IllegalStateException` |
| `Stream.toList().add(...)` | `UnsupportedOperationException` |
| Tái sử dụng Stream đã terminal | Thường ném `IllegalStateException` theo hợp đồng Stream |
| `Integer.parseInt("abc")` trong mapper | `NumberFormatException` |

**Không nên test bằng cách bắt `Exception` rồi mặc định pass**, vì có thể một exception khác biểu thị bug. Trong chương trình hoàn chỉnh, `expectThrows` kiểm tra `type.isInstance(ex)` và báo thất bại nếu không đúng loại.

Khi cần kiểm tra **message**, hãy cẩn thận: nhiều thông điệp từ JDK/collector có thể thay đổi giữa các phiên bản hoặc implementation. Tập trung assert loại exception và phần nội dung do **chính ứng dụng kiểm soát** thay vì khóa chặt một message nội bộ của JDK.

### Checked exception trong pipeline

Một mapper gọi API khai báo `throws IOException` không thể trực tiếp để checked exception thoát ra khỏi `Function.apply`. Trong một bài test liên quan I/O, cần phân biệt lỗi biên dịch do hợp đồng functional interface với lỗi runtime do I/O. Có thể bắt/bọc `UncheckedIOException` hoặc tách I/O khỏi pipeline; nhưng đây là vấn đề riêng với “nguồn rỗng/null/trùng”.

## 12. JUnit 5: từ self-test sang unit test có cấu trúc

Khi dự án đã cấu hình JUnit Jupiter, có thể chuyển các ca thử thành test method riêng. Ví dụ sau **không phải chương trình độc lập chỉ dùng JDK**; cần dependency JUnit 5 phù hợp trong Maven/Gradle và chạy bằng test runner:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class StreamEdgeCasesTest {
    @Test
    void emptyAndSingleton() {
        assertEquals(List.of(),
                Stream.<String>empty().toList());
        assertEquals(List.of("SOLO"),
                Stream.of("solo")
                        .map(String::toUpperCase)
                        .toList());
    }

    @Test
    void handlesNullByExplicitPolicy() {
        List<String> input = Arrays.asList("A", null, "B");
        assertEquals(List.of("A", "B"),
                input.stream()
                        .filter(Objects::nonNull)
                        .toList());
        assertThrows(NullPointerException.class,
                () -> input.stream()
                        .map(String::trim)
                        .toList());
    }

    @Test
    void rejectsDuplicateMapKeyUnlessMerged() {
        assertThrows(IllegalStateException.class,
                () -> Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                x -> x, String::length)));
        assertEquals(2,
                Stream.of("x", "x")
                        .collect(Collectors.toMap(
                                x -> x, x -> 1, Integer::sum))
                        .get("x"));
    }
}
```

Một test method kiểm tra **một hành vi hoặc một nhóm hành vi liên quan** sẽ dễ xác định lỗi hơn test khổng lồ chỉ có dòng in. Unit test nên dùng assertion, không chỉ so sánh bằng mắt qua stdout.

### Kiểm thử tham số hóa

Nếu có JUnit Jupiter Parameters, viết các ca input/output khác nhau thành một tập dữ liệu:

```java
// Ví dụ thành phần cho một lớp test có JUnit 5:
@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.MethodSource("cases")
void normalizedTokens(List<String> input, List<String> expected) {
    List<String> actual = input.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .map(s -> s.toLowerCase(java.util.Locale.ROOT))
            .distinct()
            .toList();
    org.junit.jupiter.api.Assertions.assertEquals(expected, actual);
}

static Stream<org.junit.jupiter.params.provider.Arguments> cases() {
    return Stream.of(
        org.junit.jupiter.params.provider.Arguments.of(
                List.of(), List.of()),
        org.junit.jupiter.params.provider.Arguments.of(
                List.of("A"), List.of("a")),
        org.junit.jupiter.params.provider.Arguments.of(
                Arrays.asList("A", null, "a"), List.of("a")),
        org.junit.jupiter.params.provider.Arguments.of(
                List.of("A", "B", "A"), List.of("a", "b"))
    );
}
```

Đây là **đoạn bổ sung** để đặt trong lớp test và có import `List`, `Arrays`, `Objects`, `Stream`. Nó yêu cầu cả phần JUnit Jupiter API và Parameters trên classpath. Không nên tự kết luận rằng dự án có sẵn JUnit từ việc đang dùng JDK 17.

## 13. Property-based thinking: kiểm tra bất biến thay vì chỉ một input

Ngoài bốn ví dụ cố định, có thể định nghĩa các **bất biến** cần giữ trên nhiều bộ dữ liệu:

1. **Lọc null:** mọi phần tử của kết quả `filter(Objects::nonNull)` đều khác null.
2. **Distinct:** kết quả không có hai phần tử khác vị trí bằng nhau theo `equals`.
3. **Giữ thứ tự:** với nguồn ordered, `distinct` giữ lần xuất hiện đầu của từng giá trị.
4. **Đếm nhóm:** tổng số phần tử ở các nhóm bằng số phần tử đầu vào, nếu mỗi đầu vào được phân loại đúng một nhóm và không bị lọc.
5. **Tần suất:** tổng các count của `groupingBy(..., counting())` bằng số phần tử đầu vào.
6. **Không mất dữ liệu:** nếu chỉ normalize mà không filter, số phần tử đầu ra bằng số phần tử đầu vào (trừ khi có lỗi/short-circuit theo hợp đồng).
7. **Idempotent normalization:** chuẩn hóa dữ liệu đã chuẩn hóa lần thứ hai cho kết quả tương đương lần thứ nhất, nếu hàm normalize được thiết kế idempotent.

Bất biến có thể được kiểm tra bằng một thư viện property-based test hoặc test lặp với input tạo có kiểm soát. Tuy nhiên **không dùng random thiếu seed mà phụ thuộc vào kết quả không tái lập được**: khi có lỗi, phải lưu input/seed để chẩn đoán.

Ví dụ ý tưởng bất biến cho `distinct`:

```java
List<String> result = input.stream().distinct().toList();

long distinctCount = result.stream().distinct().count();
if (distinctCount != result.size()) {
    throw new AssertionError("duplicate remained");
}
```

Đây là đoạn minh họa, cần có biến `input`. Test này chỉ kiểm tra **không còn trùng**; để chắc chắn không bỏ sót nhóm giá trị, cần so sánh tập giá trị hoặc danh sách lần xuất hiện đầu với expected reference implementation.

## 14. Nguồn tùy chỉnh: kiểm tra rỗng, một phần tử và trùng

Một `Iterable` hoặc `Spliterator` tùy chỉnh có thể có lỗi ở **phần sinh dữ liệu**, độc lập với các operation của Stream. Ví dụ:

```java
Iterable<String> source = () ->
        java.util.Arrays.asList("a", "a", null).iterator();

List<String> result = StreamSupport
        .stream(source.spliterator(), false)
        .filter(java.util.Objects::nonNull)
        .distinct()
        .toList();

System.out.println(result); // [a]
```

Nguồn trên dùng `Iterable.spliterator()` và được bọc qua `StreamSupport`; `filter`/`distinct` vẫn có ý nghĩa như với collection thông thường.

Nếu bạn tự triển khai `Spliterator.tryAdvance`/`trySplit`, hãy kiểm thử thêm:

- **Nguồn rỗng:** `tryAdvance` trả false ngay, `count()` bằng 0.
- **Một phần tử:** `tryAdvance` trả true một lần rồi false, không phát trùng.
- **Null:** nếu quảng bá `NONNULL` thì nguồn không được phát null.
- **Trùng:** nếu quảng bá `DISTINCT` thì không được phát hai giá trị bằng nhau theo `equals`.
- **Có thứ tự:** nếu quảng bá `ORDERED` thì thứ tự kết quả phải đúng hợp đồng.
- **Kích thước:** nếu quảng bá `SIZED` thì kích thước phải chính xác trong điều kiện được cam kết.
- **Chia nguồn:** `trySplit` không được mất hoặc lặp phần tử, kể cả với 0/1/2 phần tử.

**Đừng khai `DISTINCT` chỉ vì mong downstream tự loại trùng.** Nếu nguồn thực có trùng nhưng Spliterator quảng bá `DISTINCT` sai, Stream framework có thể tối ưu bỏ qua phép `distinct()`. Đây là một lỗi metadata nguồn, không phải lỗi của `distinct`.

### Test theo nhiều lần split

Đối với Spliterator có thể chia:

```text
Nguồn: [A, B, C, D]
       |
       +-- trySplit() --> nhánh trái
       |
       +--------------> nhánh phải
```

Hãy thu thập các phần tử của cả hai nhánh rồi xác minh **tổng số phần tử**, **giá trị**, **không trùng ngoài mong đợi**, và nếu `ORDERED` thì **thứ tự hợp lệ**. Nguồn rỗng và singleton thường làm lộ bug `trySplit` trả một nhánh trống nhưng báo kích thước sai hoặc không cập nhật cursor.

## 15. Khi nào dữ liệu trùng là lỗi, khi nào là nghiệp vụ bình thường?

Không phải tất cả dữ liệu trùng đều phải được `distinct()` loại bỏ.

| Tình huống | Cách xử lý có thể phù hợp |
| --- | --- |
| Một người dùng được import hai lần với cùng ID | Validate, cảnh báo hoặc gộp theo quy tắc |
| Cùng sản phẩm xuất hiện ở hai dòng hóa đơn | Có thể giữ cả hai dòng để cộng số lượng |
| Cùng từ xuất hiện nhiều lần trong văn bản | `groupingBy(..., counting())` để đếm tần suất |
| Danh sách tag lặp cùng nhãn | `distinct()` để hiển thị mỗi tag một lần |
| Hai object khác nhau nhưng cùng mã nghiệp vụ | Nhóm theo key, đừng chỉ gọi `distinct()` trên object |
| Trùng khóa trong `toMap` | Định nghĩa merge hoặc báo lỗi, không chọn ngẫu nhiên |
| Bản ghi duplicate do retry I/O | Idempotency, unique constraint và audit ở tầng lưu |
| Duplicate null trong danh sách | Có thể có một phần tử null sau `distinct`, nếu giữ null hợp lệ |

Với nghiệp vụ cần toàn vẹn dữ liệu, “xóa bản trùng” không phải lúc nào là sửa đúng. Chẳng hạn nếu hai đơn thanh toán có cùng ID nhưng tổng tiền khác nhau, việc chỉ `distinct` theo ID và giữ một record có thể giấu lỗi nghiêm trọng. Test phải xác định **nguyên tắc xử lý xung đột**.

## 16. Test nguồn null và null phần tử phải tách riêng

Ví dụ một API cũ có thể trả cả `null` thay vì danh sách:

```java
List<String> legacy = null;
```

Dùng `legacy.stream()` ném `NullPointerException` ngay tại nguồn. Nếu hợp đồng của API cũ cho phép vắng mặt, một adapter rõ ràng là:

```java
List<String> safeSource =
        legacy == null ? List.of() : legacy;

List<String> result = safeSource.stream()
        .filter(java.util.Objects::nonNull)
        .toList();
```

Đây là đoạn minh họa. **Không tự động quy mọi null nguồn thành empty** khi null thực sự biểu thị lỗi kết nối, dữ liệu chưa tải hoặc vi phạm hợp đồng. Trong các trường hợp ấy, cần báo lỗi/Result cụ thể.

Một cách dùng `Optional`:

```java
List<String> result =
        java.util.Optional.ofNullable(legacy)
                .orElseGet(List::of)
                .stream()
                .filter(java.util.Objects::nonNull)
                .toList();
```

Cả hai cách đều có cùng kết quả khi `legacy == null` và policy đã xác định “null nguồn = không có phần tử”. Khác biệt với `Stream.ofNullable` là đối tượng được kiểm tra ở đây là **danh sách nguồn**, không phải từng phần tử của một Stream.

## 17. Tránh test phụ thuộc thứ tự ngẫu nhiên

Với `HashSet` hoặc `HashMap`, không viết test kỳ vọng thứ tự tùy hứng nếu API không cam kết encounter order. Chẳng hạn:

```java
java.util.Set<String> set =
        new java.util.HashSet<>(List.of("B", "A", "C"));

List<String> sorted = set.stream()
        .sorted()
        .toList();

System.out.println(sorted); // [A, B, C]
```

Lời gọi `sorted()` khiến kết quả có thứ tự xác định. Nếu bỏ nó, thứ tự từ `HashSet` không nên là một yêu cầu của test.

Với parallel stream trên nguồn ordered, `distinct` và `toList` vẫn bảo toàn encounter order theo contract. Nhưng **thứ tự thực thi mapper hoặc `forEach` không được bảo đảm**. Kiểm thử kết quả bằng collection/những bất biến, không assert thứ tự log hay thread name.

### Test không nên giả định thứ tự `groupingBy` mặc định

`Collectors.groupingBy(...)` trả map không bảo đảm thứ tự iteration. Với test:

```java
Map<String, Long> grouped = words.stream()
        .collect(Collectors.groupingBy(
                Function.identity(), Collectors.counting()));

assertEquals(2L, grouped.get("a"));
assertEquals(1L, grouped.get("b"));
```

Đây là đoạn JUnit minh họa, cần định nghĩa `words` và import assertions. Nếu phải có thứ tự khóa, chọn một `TreeMap`/`LinkedHashMap` theo yêu cầu thực sự, hoặc `sorted` khi duyệt kết quả.

## 18. Test không chỉ “đúng output” mà còn phải biết vì sao đúng

Một bộ test tốt nên gồm:

**Expected normal result:** dữ liệu hợp lệ trả đúng List/Map/số.

**Expected exception:** null hoặc duplicate không hợp lệ phải báo lỗi đúng kiểu, không bị nuốt.

**Boundary:** empty, singleton, duplicate sát nhau/không sát nhau, null ở đầu/giữa/cuối.

**Invariant:** không mất phần tử ngoài những bước lọc/khử trùng đã định nghĩa; count, order, groups đúng.

**Resource and lifecycle:** nguồn Stream không tái sử dụng; iterator một lần; nguồn I/O được đóng khi cần.

**Concurrency:** nếu pipeline parallel hoặc nguồn concurrent, kiểm tra không race và không phụ thuộc thứ tự thread.

**Domain policy:** phân biệt “không tìm thấy” với “tải thất bại”, “bản ghi trùng hợp lệ” với “xung đột ID”, “null được phép” với “null vi phạm schema”.

Thường nên tổ chức test thành các nhóm rõ: `emptySource`, `singletonSource`, `nullSource`, `nullElements`, `duplicateValues`, `duplicateBusinessKeys`, `parallelOrderedResult` và `customSpliterator`. Việc đặt tên giúp người duy trì hiểu ngay lý do một ca thử thất bại.

## 19. Những lỗi thường gặp và hướng sửa

| Sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Chỉ test danh sách nhiều phần tử | Bỏ sót empty/singleton | Ma trận test theo kích thước 0,1,n |
| `findFirst().get()` trên nguồn rỗng | Optional rỗng | `orElse`/`orElseThrow` đúng chính sách |
| Nghĩ `allMatch` trên empty là false | Logic lượng từ của Stream | Assert `true` và xác thực nonempty riêng |
| Nhầm List null với List có phần tử null | Khác thời điểm/lỗi | Test hai đầu vào riêng |
| Dùng `List.of(null)` để tạo fixture | Factory cấm null | Dùng `Arrays.asList`/`ArrayList` nếu cần fixture nullable |
| `Stream.of((String)null)` được coi là empty | Thực tế có một phần tử null | `Stream.ofNullable` nếu cần empty |
| `map(String::trim)` trước lọc null | NPE khi gặp null | Lọc/validate trước |
| Nghĩ `Stream.toList` cấm null | API cho phép null | Đối chiếu với `toUnmodifiableList` |
| `groupingBy(Function.identity())` với null | Null classifier key không hợp lệ | Chuẩn hóa key hoặc fail-fast |
| `distinct` trước normalize | Trùng theo ngữ nghĩa không bị loại | Chuẩn hóa trước |
| `distinct` trên record để loại trùng ID | Record equality gồm các component | `map(Order::id)` hoặc nhóm theo ID |
| `toMap` không có merge khi key trùng | `IllegalStateException` | Kiểm tra/xử lý xung đột hoặc merge rõ |
| Dùng `Collectors.toSet` rồi assert thứ tự | Set result không bảo đảm thứ tự | `distinct().toList()` trên ordered stream |
| Dùng `HashMap.toString()` làm expected exact | Thứ tự key không được bảo đảm | Assert từng entry hoặc map có thứ tự |
| Test chỉ in console | Không tự phát hiện sai | Dùng assertions và fail rõ |
| Bắt mọi exception rồi cho pass | Bug khác cũng được nhận là đúng | Assert đúng loại exception |
| Tự quảng bá `DISTINCT`/`NONNULL` cho Spliterator sai | Có thể gây tối ưu sai | Metadata phải phản ánh nguồn thật |
| Dùng lại stream sau terminal | Stream đã tiêu thụ | Tạo nguồn stream mới |
| Bỏ mất duplicate bằng `distinct` ở dữ liệu cần kiểm toán | Che lỗi hoặc mất số lượng | Giữ raw input, đếm và validate theo domain |
| Assert thứ tự các thread parallel | Lịch chạy không xác định | Assert output/đặc tính, không assert log |

## 20. Bài tập thực hành

1. Viết bảng kết quả của `Stream.<Integer>empty().count()`, `findFirst()`, `anyMatch`, `allMatch`, `noneMatch`. Giải thích vì sao `allMatch` là true trên empty.
2. Với `List.of("A")`, kiểm tra `limit(0)`, `limit(1)`, `skip(1)`, `distinct` và `findFirst`. Ghi kiểu kết quả của mỗi terminal.
3. Tạo nguồn `Arrays.asList("A", null, "B")`. Thử `map(String::trim)` trước và sau `filter(Objects::nonNull)`; trường hợp nào ném NPE?
4. So sánh `Stream.of((String)null).count()` với `Stream.ofNullable((String)null).count()`. Vì sao một kết quả là 1 còn một kết quả là 0?
5. Thử `Stream.of((String)null).findFirst()` và kiểm thử loại exception; vì sao Optional không thể biểu diễn giá trị null “có mặt”?
6. Dùng `Collectors.groupingBy(Function.identity())` trên nguồn chứa null; sửa bằng khóa `"MISSING"` khi nghiệp vụ cho phép.
7. Tạo `List.of("Java"," java ","JAVA")`, thử `distinct` trước chuẩn hóa và sau chuẩn hóa. Viết expected results.
8. Tạo `record Order(String id,int amount)` với hai record cùng ID nhưng khác amount. Vì sao `distinct()` trên record khác `map(Order::id).distinct()`?
9. Dùng `groupingBy(Function.identity(), counting())` để đếm `[a,b,a,c,a]`. Kiểm tra count a=3, b=1, c=1.
10. Dùng `toMap` với hai khóa `"x"`. Kiểm thử `IllegalStateException` rồi định nghĩa merge function cộng tần suất.
11. Viết một unit test có `assertThrows` cho `List.of((String)null)` và một test khác cho `Collectors.toUnmodifiableList` chứa null.
12. Tạo `Iterable` tùy chỉnh trả ba phần tử `["x","x",null]`. Dùng `StreamSupport` và pipeline lọc null/`distinct`; expected là `["x"]`.
13. Tạo Spliterator tùy chỉnh quảng bá `ORDERED`/`SIZED` đúng, test empty/singleton/đa phần tử, `tryAdvance` và `trySplit`.
14. So sánh `List.of("b","a","b").parallelStream().distinct().toList()` với `HashSet.stream().toList()`. Khi nào thứ tự kết quả cần được assert?
15. Dùng `TreeMap::new` với `groupingBy` và viết expected output có thứ tự key. Vì sao không nên dựa vào thứ tự `HashMap`?
16. Viết một policy cho dữ liệu import: bản ghi trùng hoàn toàn thì bỏ qua, cùng ID nhưng khác nội dung thì báo xung đột, thiếu ID thì lỗi. Chọn pipeline/collector và ca test thích hợp.
17. Viết test trên dữ liệu tạo có kiểm soát để kiểm tra bất biến tổng count sau `groupingBy` bằng kích thước đầu vào (khi không có lọc).
18. Tạo một `List<String>` mutable nguồn bằng null, rồi một list hợp lệ chứa phần tử null. Viết hai test khác nhau và giải thích chính sách khi nguồn không tồn tại.
19. Nếu một lần xử lý thất bại do nguồn file không mở được, có nên trả `Stream.empty()` như dữ liệu rỗng thật không? Nêu khác biệt nghiệp vụ và cách báo lỗi.
20. Chuyển chương trình `StreamEdgeCasesDemo` thành các test JUnit riêng cho từng loại dữ liệu; giữ ca expected-exception và không phụ thuộc vào thứ tự thực thi parallel.

## 21. Checklist nghiệm thu bài kiểm thử Stream

- Đã có test với **0 phần tử, 1 phần tử và nhiều phần tử**?
- Đã tách rõ **nguồn null** và **phần tử null trong nguồn**?
- Chính sách với `null` là giữ, lọc, thay thế hay báo lỗi? Test có thể hiện điều đó không?
- Có phân biệt `Stream.of(null)` với `Stream.ofNullable(null)` không?
- Có test cả giá trị trùng hoàn toàn và **trùng khóa nghiệp vụ**?
- `distinct` dùng equality đúng mục đích chưa? Đã normalize trước nếu cần?
- `groupingBy`/`toMap` có key null hoặc duplicate không? Đã quy định cách xử lý?
- Các terminal trả Optional trên empty đã được xử lý rõ chưa?
- Có kiểm tra `anyMatch`/`allMatch`/`noneMatch` trên empty?
- Có test bảo toàn số lượng, không mất dữ liệu trái mục đích và thứ tự khi nguồn ordered?
- Có dùng assertions thay cho chỉ in kết quả ra stdout?
- Có cố định expected exceptions theo contract, tránh bắt mọi lỗi rồi mặc định pass?
- Có test nguồn tự viết, `tryAdvance`/`trySplit`/characteristics nếu sử dụng StreamSupport?
- Có tránh assert thứ tự `HashMap`/`HashSet` và lịch thực thi mapper parallel?
- Có test cách xử lý lỗi I/O, lifecycle và retry ở tầng phù hợp nếu dữ liệu từ nguồn ngoài?
- Có ghi lại seed/input khi dùng dữ liệu sinh ngẫu nhiên để tái hiện ca lỗi?

**Kết luận:** Để kiểm tra pipeline Java Stream đáng tin cậy, hãy chủ động thử **nguồn rỗng**, **một phần tử**, **nguồn hoặc phần tử null**, và **giá trị/khóa trùng**. Mỗi tình huống phải có expected result hoặc expected exception rõ ràng. Dùng `Objects::nonNull`/`Stream.ofNullable` khi chính sách cho phép bỏ null, `distinct` sau chuẩn hóa khi cần loại trùng về ngữ nghĩa, và `groupingBy`/`toMap` với quy tắc trùng khóa phù hợp. Assertion tự động và kiểm tra bất biến quan trọng hơn một lần nhìn stdout thấy “có vẻ đúng”.
