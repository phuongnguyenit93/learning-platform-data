# Quy tắc `null` của khóa, giá trị và các hàm truyền vào `Collectors.toUnmodifiableMap` (Java 10+)

## 1. Mục tiêu: phân biệt ba loại `null`

Từ **Java 10**, `java.util.stream.Collectors.toUnmodifiableMap(...)` tạo một `Collector` gom các phần tử của `Stream<T>` thành **`Map<K,V>` không sửa được**. Phương thức này có hai overload:

- `toUnmodifiableMap(keyMapper, valueMapper)`: không cho khóa trùng nhau.
- `toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`: cho phép đặt cách kết hợp giá trị khi khóa trùng.

**Quy tắc quan trọng nhất:** cả hai overload đều **không cho kết quả cuối chứa khóa `null` hoặc giá trị `null`**. Hơn nữa, chính các hàm được truyền làm đối số cũng phải khác `null`. Hai loại điều kiện này được kiểm tra ở các thời điểm khác nhau.

Cần phân biệt bốn tình huống sau:

| Tình huống | Hành vi |
| --- | --- |
| Đối số `keyMapper` là `null` | Ném `NullPointerException` khi **tạo Collector** |
| Đối số `valueMapper` là `null` | Ném `NullPointerException` khi **tạo Collector** |
| Đối số `mergeFunction` là `null` ở overload ba đối số | Ném `NullPointerException` khi **tạo Collector** |
| Hàm `keyMapper` hoặc `valueMapper` hợp lệ **trả về `null`** cho một phần tử | Ném `NullPointerException` trong quá trình **thu thập**; Map kết quả không được tạo thành công |
| `mergeFunction` hợp lệ **trả về `null`** khi giải quyết khóa trùng | Theo ngữ nghĩa `Map.merge`, **bỏ ánh xạ của khóa đó**, không phải lưu giá trị `null` |

Dòng cuối là một sắc thái rất dễ nhầm: **“hàm merge là `null`”** và **“hàm merge trả về `null`”** là hai sự kiện hoàn toàn khác nhau.

Đây là những quy tắc API vẫn áp dụng trong Java hiện đại, không phải mẹo của bản JDK cụ thể. Không suy luận rằng mọi Collector tạo map đều có chính xác cùng quy tắc null.

## 2. Hai chữ ký và vai trò của từng hàm

API có chữ ký tổng quát, viết rút gọn:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
~~~

Đây là **chữ ký tham khảo từ thư viện**, không phải hai phương thức cần tự định nghĩa trong lớp.

`T` là kiểu phần tử của stream; `K` là kiểu khóa; `U` là kiểu giá trị. Các hàm:

1. **`keyMapper`:** nhận một phần tử `T` và tính ra khóa `K`.
2. **`valueMapper`:** nhận cùng phần tử `T` và tính ra giá trị `U`.
3. **`mergeFunction`:** chỉ được cung cấp ở overload ba đối số, dùng để giải quyết nhiều giá trị cùng một khóa, theo ngữ nghĩa kết hợp được mô tả bởi `Map.merge`.

Ví dụ đúng với hai mapper không null và không trùng khóa:

~~~java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Các lệnh đặt trong phương thức:
Map<String, Integer> prices = Stream.of("A:2", "B:4")
        .collect(Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2))));

System.out.println(prices.get("A")); // 2
System.out.println(prices.get("B")); // 4
~~~

Kết quả không sửa được: `prices.put("C", 5)` biên dịch được theo giao diện `Map` nhưng khi chạy sẽ ném `UnsupportedOperationException`.

## 3. `keyMapper` là `null` — lỗi ngay khi xây dựng collector

Một **hàm** `keyMapper` là đối số kiểu `Function`. Nó không được phép là tham chiếu `null`:

~~~java
// Đoạn lỗi cố ý (đừng đưa vào chương trình chạy thành công):
var collector = Collectors.<String, String, Integer>
        toUnmodifiableMap(null, String::length);
// Ném NullPointerException ngay tại lời gọi toUnmodifiableMap.
~~~

Điều quan trọng là **lỗi xảy ra trước khi duyệt stream**. Không cần có phần tử đầu vào, và không cần gọi `collect` rồi mới phát hiện đối số function không hợp lệ.

Một trường hợp thực tế:

~~~java
java.util.function.Function<String, String> keyMapper = null;

var empty = java.util.stream.Stream.<String>empty();

// empty.collect(Collectors.toUnmodifiableMap(
//         keyMapper, String::length));
// Vẫn không được: Collectors.toUnmodifiableMap nhận keyMapper null.
~~~

**Stream rỗng không miễn trừ việc kiểm tra chính tham số mapper.** Nếu cần truyền hàm có thể được cấu hình động, hãy kiểm tra nó đã được tạo đúng trước khi truyền vào `Collectors.toUnmodifiableMap`.

## 4. `valueMapper` là `null` — cũng lỗi khi xây dựng collector

Tương tự:

~~~java
// Đoạn lỗi cố ý:
var collector = Collectors.<String, String, Integer>
        toUnmodifiableMap(
                java.util.function.Function.identity(),
                null);
// Ném NullPointerException: tham chiếu valueMapper là null.
~~~

Ở đây, `null` là **đối tượng function** được truyền vào; nó không phải giá trị do function tính ra.

Nếu lập trình viên chỉ muốn biến đổi giá trị theo một công thức đơn giản, dùng một lambda hợp lệ:

~~~java
var collector = Collectors.toUnmodifiableMap(
        (String s) -> s,
        (String s) -> s.length());
~~~

Trong đoạn thứ hai, cả hai mapper đều là các đối tượng hàm hợp lệ. Việc chúng có trả về null hay không còn phải xét theo dữ liệu khi `collect` thực thi.

## 5. `mergeFunction` là `null` ở overload ba đối số

Overload thứ ba yêu cầu đối số `mergeFunction` khác null ngay cả khi đầu vào **không có khóa trùng**:

~~~java
// Đoạn lỗi cố ý:
var collector = Collectors.<String, String, Integer>
        toUnmodifiableMap(
                java.util.function.Function.identity(),
                String::length,
                null);
// Ném NullPointerException ngay khi tạo Collector.
~~~

Không thể dùng `null` với ý nghĩa “tôi không cần xử lý duplicate”. Nếu nguồn được bảo đảm không trùng khóa, hãy chọn **overload hai đối số**. Nếu nguồn có thể trùng, hãy truyền một `BinaryOperator<U>` hợp lệ, có chính sách xử lý rõ.

~~~java
var collector = Collectors.toUnmodifiableMap(
        (String s) -> s.substring(0, 1),
        (String s) -> Integer.parseInt(s.substring(2)),
        Integer::sum); // mergeFunction là method reference hợp lệ
~~~

**Lưu ý:** `mergeFunction` không thể là null khác với câu hỏi **kết quả trả về của merge function có thể là null không**. Chúng là hai vấn đề riêng; phần 8 giải thích kết quả null của hàm merge.

## 6. `keyMapper` hợp lệ nhưng **trả về `null`** — lỗi khi collect

Giả sử mapper là lambda hợp lệ nhưng trả về null với một số dữ liệu:

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.equals("B") ? null : s, // B -> khóa null
                String::length));
// Ném NullPointerException trong quá trình collect.
~~~

Không có kết quả kiểu `Map` chứa ánh xạ `null -> 1`. `toUnmodifiableMap` không chấp nhận khóa null.

Tại sao cần phân biệt thời điểm?

- `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` nhận **hai đối tượng hàm khác null**, nên việc tạo collector thành công.
- Khi stream được xử lý, `keyMapper.apply("B")` tạo **giá trị khóa null**.
- Hợp đồng collector cấm khóa null và ném `NullPointerException`; không tạo một map unmodifiable chứa null.

Không nên dựa vào việc ngoại lệ xuất hiện trong accumulator hay finisher, vì chi tiết triển khai có thể thay đổi. Điều chắc chắn theo API là **kết quả có khóa null không được chấp nhận**.

### Không nhầm với `Map` mutable

Một số implementation như `HashMap` có thể chứa khóa null. Nhưng collector đang xét **không được định nghĩa là “cứ tạo một HashMap rồi giữ nguyên tất cả khả năng của nó”**. Đích của `toUnmodifiableMap` là map không sửa được **không có khóa/giá trị null**. Đừng suy luận quy tắc của `HashMap` sang API collector này.

## 7. `valueMapper` hợp lệ nhưng **trả về `null`** — cũng lỗi khi collect

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                java.util.function.Function.identity(),
                s -> s.equals("B") ? null : s.length()));
// Ném NullPointerException vì valueMapper("B") là null.
~~~

Trường hợp này độc lập với việc khóa có trùng hay không. Ví dụ trên có các khóa `"A"` và `"B"` khác nhau; nó vẫn thất bại vì giá trị cho `"B"` là null.

Điểm cần nhớ:

- **Giá trị `null` không phải một “ô trống hợp lệ”** trong map do `toUnmodifiableMap` tạo.
- **Không được trông đợi collector tự loại bản ghi có value null.**
- Không được chờ hàm merge xử lý các value null: `valueMapper` được yêu cầu trả về giá trị hợp lệ trước khi giải quyết khóa trùng.

Một lỗi thực tế thường gặp là viết `record -> record.getOptionalField()` khi getter có thể trả null. Nếu dữ liệu không đầy đủ, cần chọn chính sách **báo lỗi, loại bản ghi, hoặc thay giá trị** trước khi gọi collector, thay vì tạo value null rồi mong nó tự xử lý.

## 8. Khóa trùng, hàm merge và một trường hợp `null` rất đặc biệt

### Không có merge function: trùng khóa gây `IllegalStateException`

~~~java
var result = java.util.stream.Stream.of("A:2", "A:3")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2))));
// Ném IllegalStateException vì hai phần tử cùng khóa "A".
~~~

Đây là **lỗi trùng khóa**, không phải NPE. `toUnmodifiableMap(keyMapper, valueMapper)` hai đối số yêu cầu khóa kết quả là duy nhất theo `equals`.

### Có merge function: giải quyết trùng theo chính sách

~~~java
var merged = java.util.stream.Stream.of("A:2", "A:3", "B:4")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2)),
                Integer::sum));

System.out.println(merged.get("A")); // 5
System.out.println(merged.get("B")); // 4
~~~

`Integer::sum` là hàm hợp lệ không null; khi gặp hai giá trị `2` và `3` cùng khóa `A`, collector gộp thành `5`. Bản đồ kết quả vẫn không sửa được.

### `mergeFunction` **trả về `null`**: loại ánh xạ, không lưu null

Theo API, merge function được dùng theo ngữ nghĩa của `Map.merge`. Với `Map.merge`, nếu hàm kết hợp trả về `null`, **ánh xạ của khóa liên quan được xóa**. Do vậy:

~~~java
var removed = java.util.stream.Stream.of("A:2", "A:3")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2)),
                (oldValue, newValue) -> null));

System.out.println(removed.size()); // 0
~~~

**Ví dụ đã được kiểm thử trên JDK 24.** Khi phần tử thứ hai có cùng khóa `"A"`, `mergeFunction` **được gọi và trả về null**, khiến ánh xạ `"A"` bị loại khỏi kết quả. Không có ánh xạ `A -> null`, nên không vi phạm quy tắc “map kết quả không chứa null”.

Phân biệt ba trường hợp:

| Trường hợp | Hành vi |
| --- | --- |
| Đối số `mergeFunction = null` | `NullPointerException` khi tạo collector |
| `valueMapper` trả `null` | `NullPointerException` khi thu thập |
| `mergeFunction` hợp lệ trả `null` khi khóa trùng | Xóa ánh xạ tương ứng theo `Map.merge` |

**Cảnh báo:** dùng `null` từ merge function để xóa khóa là ngữ nghĩa của phép merge, **không phải cách tự động lọc mọi bản ghi có dữ liệu null**. Với một khóa xuất hiện thêm lần nữa sau khi bị xóa, ánh xạ có thể lại được bổ sung. Nếu bài toán cần “bỏ mọi bản ghi thiếu dữ liệu”, lọc bằng `Stream.filter` thường minh bạch hơn.

Không nên mô tả tất cả hàm trả về null đều bị từ chối, vì điều đó làm sai trường hợp đặc biệt của `mergeFunction`.

## 9. Phần tử đầu vào của `Stream` là `null`: điều kiện khác với khóa/giá trị null

`Stream<T>` có thể chứa một **phần tử null** nếu nguồn stream cho phép. `toUnmodifiableMap` không nói “cấm mọi phần tử đầu vào null” theo cách độc lập với mapper; điều nó yêu cầu là **khóa và giá trị được ánh xạ đều không null**.

Nếu mapper đủ an toàn với phần tử null và tạo ra khóa/giá trị khác null, phép thu thập có thể thành công:

~~~java
var result = java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s == null ? "MISSING" : s,
                s -> s == null ? 0 : s.length()));

System.out.println(result.get("MISSING")); // 0
~~~

Đây là ví dụ đã được chạy kiểm tra. Đối tượng nguồn `null` được mapper chuyển thành **khóa `"MISSING"` và giá trị `0`**, cả hai hợp lệ. Nếu thay bằng `String::length` mà nhận một phần tử null, bản thân lời gọi `length` sẽ gây NPE; đó là lỗi **bên trong mapper**, chứ không chứng minh một quy tắc mới rằng mọi stream null đều bị collector chặn ngay lúc nhận.

Với dữ liệu nghiệp vụ, **không nên tự mã hóa mọi null thành cùng một khóa `"MISSING"`** nếu nhiều bản ghi thiếu có ý nghĩa khác nhau: chúng có thể gây **duplicate key**. Hãy xác định rõ chính sách trước khi chuyển null thành sentinel.

Một lựa chọn rõ ràng hơn khi null nghĩa là “không có bản ghi”:

~~~java
var result = java.util.stream.Stream.<String>of("A", null, "B")
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                java.util.function.Function.identity(),
                String::length));
~~~

Lúc này `null` bị loại **trước khi chạy mapper**. Chỉ làm vậy khi hợp đồng nghiệp vụ thực sự cho phép bỏ bản ghi null.

## 10. Chương trình hoàn chỉnh và `stdout` có thể kiểm chứng

Lưu thành **`UnmodifiableMapNullRulesDemo.java`**:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnmodifiableMapNullRulesDemo {

    private static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=unexpected");
        } catch (NullPointerException ex) {
            System.out.println(label + "=NPE");
        }
    }

    private static void expectIse(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=unexpected");
        } catch (IllegalStateException ex) {
            System.out.println(label + "=ISE");
        }
    }

    public static void main(String[] args) {
        var ok = Stream.of("A:2", "B:4")
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.substring(0, 1),
                        s -> Integer.parseInt(s.substring(2))));

        System.out.println("okSize=" + ok.size());
        System.out.println("okA=" + ok.get("A"));

        // Hai mapper hợp lệ nhưng sinh key hoặc value null.
        expectNpe("nullKey", () -> Stream.of("A", "B")
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.equals("B") ? null : s,
                        String::length)));

        expectNpe("nullValue", () -> Stream.of("A", "B")
                .collect(Collectors.toUnmodifiableMap(
                        Function.identity(),
                        s -> s.equals("B") ? null : s.length())));

        // Chính các đối số hàm là null: lỗi khi tạo collector.
        expectNpe("nullKeyMapper", () ->
                Collectors.<String, String, Integer>toUnmodifiableMap(
                        null, String::length));

        expectNpe("nullValueMapper", () ->
                Collectors.<String, String, Integer>toUnmodifiableMap(
                        Function.identity(), null));

        expectNpe("nullMergeFunction", () ->
                Collectors.<String, String, Integer>toUnmodifiableMap(
                        Function.identity(), String::length, null));

        // Khóa trùng, không có merge function.
        expectIse("duplicateKey", () -> Stream.of("A:2", "A:3")
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.substring(0, 1),
                        s -> Integer.parseInt(s.substring(2)))));

        // Có merge function hợp lệ.
        Map<String, Integer> merged =
                Stream.of("A:2", "A:3", "B:4")
                        .collect(Collectors.toUnmodifiableMap(
                                s -> s.substring(0, 1),
                                s -> Integer.parseInt(s.substring(2)),
                                Integer::sum));

        System.out.println("mergedA=" + merged.get("A"));
        System.out.println("mergedB=" + merged.get("B"));

        // Kết quả hàm merge là null -> xóa ánh xạ A.
        var removed = Stream.of("A:2", "A:3")
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.substring(0, 1),
                        s -> Integer.parseInt(s.substring(2)),
                        (x, y) -> null));

        System.out.println("nullMergeResultSize=" + removed.size());

        // Stream element null được mapper xử lý hợp lệ.
        var handledNullElement = Stream.<String>of("A", null)
                .collect(Collectors.toUnmodifiableMap(
                        s -> s == null ? "MISSING" : s,
                        s -> s == null ? 0 : s.length()));

        System.out.println("nullElementHandled="
                + handledNullElement.get("MISSING"));

        try {
            ok.put("C", 5);
        } catch (UnsupportedOperationException ex) {
            System.out.println("put=blocked");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**. Tất cả API và cú pháp chương trình đã có từ **Java 10**:

~~~bash
javac UnmodifiableMapNullRulesDemo.java
java UnmodifiableMapNullRulesDemo
~~~

**`stdout`:**

~~~text
okSize=2
okA=2
nullKey=NPE
nullValue=NPE
nullKeyMapper=NPE
nullValueMapper=NPE
nullMergeFunction=NPE
duplicateKey=ISE
mergedA=5
mergedB=4
nullMergeResultSize=0
nullElementHandled=0
put=blocked
~~~

Cách đọc kết quả:

1. `okSize=2`, `okA=2`: hai mapper tạo các khóa/giá trị hợp lệ.
2. `nullKey=NPE` và `nullValue=NPE`: kết quả mapper trả null trong lúc collect bị từ chối.
3. Ba dòng `null...Mapper=NPE` / `nullMergeFunction=NPE`: **đối số hàm là null** nên không thể tạo collector tương ứng.
4. `duplicateKey=ISE`: overload hai đối số không chấp nhận khóa trùng theo `equals`.
5. `mergedA=5`, `mergedB=4`: overload ba đối số giải quyết trùng khóa bằng `Integer::sum`.
6. `nullMergeResultSize=0`: hàm merge trả null, ánh xạ đã bị xóa theo `Map.merge`.
7. `nullElementHandled=0`: phần tử stream null được mapper xử lý thành khóa/giá trị hợp lệ.
8. `put=blocked`: Map trả về không sửa được, gọi `put` gây `UnsupportedOperationException`.

Bài kiểm tra không in trực tiếp toàn bộ map, vì map do `toUnmodifiableMap` tạo **không cam kết thứ tự duyệt**. Các giá trị trên dùng `get`/`size` nên ổn định.

## 11. Thiết kế xử lý null trong ứng dụng

### A. Báo lỗi rõ ràng khi nguồn thiếu trường bắt buộc

Khi mỗi bản ghi buộc phải có khóa và giá trị, có thể chủ động kiểm tra trước hoặc ngay trong mapper:

~~~java
record UserRole(String userId, String role) {}

// Đoạn minh họa bên trong phương thức:
var result = users.stream()
        .collect(Collectors.toUnmodifiableMap(
                user -> java.util.Objects.requireNonNull(
                        user.userId(), "userId must not be null"),
                user -> java.util.Objects.requireNonNull(
                        user.role(), "role must not be null")));
~~~

Ở đây `UserRole` là một kiểu record ví dụ; `users` được giả định có kiểu `Collection<UserRole>` hoặc kiểu hỗ trợ `stream()`. **Record là tính năng chuẩn từ Java 16**, nên đoạn minh họa này yêu cầu **JDK 17+**; phần API `toUnmodifiableMap` vẫn có từ Java 10.

Nếu muốn giữ khả năng biên dịch Java 10, dùng một lớp thông thường với getter tương ứng. Điều quan trọng không phải record, mà là **mapper phải cho ra khóa/giá trị khác null**. `Objects.requireNonNull` giúp tạo thông báo cụ thể khi dữ liệu vi phạm hợp đồng.

### B. Bỏ bản ghi có khóa hoặc giá trị thiếu — chỉ khi được phép

Giả sử dữ liệu có thể không đầy đủ và nghiệp vụ cho phép bỏ toàn bộ bản ghi thiếu:

~~~java
// Trong một phương thức, users là Stream<User> hoặc danh sách User.
// User có phương thức userId() và role() trả String.

var result = users.stream()
        .filter(u -> u != null
                && u.userId() != null
                && u.role() != null)
        .collect(Collectors.toUnmodifiableMap(
                u -> u.userId(),
                u -> u.role()));
~~~

**Cảnh báo:** đây là **mã minh họa cần một lớp `User` tương ứng**, không phải chương trình độc lập. Điều kiện lọc có thể làm mất dữ liệu; chỉ sử dụng nếu "bỏ bản ghi thiếu" là yêu cầu nghiệp vụ thật. Sau lọc, **vẫn phải xử lý khả năng trùng khóa** (qua dữ liệu không trùng hoặc overload ba đối số).

Khi dữ liệu có thể thay đổi từ luồng khác, bước lọc và bước thu thập không tự bảo đảm snapshot nhất quán; cần thiết kế truy cập đồng thời phù hợp.

### C. Thay `null` bằng một giá trị có nghĩa

~~~java
var result = java.util.stream.Stream.<String>of("A", null)
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s == null ? "<MISSING>" : s,
                s -> s == null ? 0 : s.length()));
~~~

Cách này hợp lệ về kỹ thuật, nhưng **khóa `"<MISSING>"` có thể va chạm** với một giá trị thật hoặc với bản ghi thiếu khác. Cần thiết kế khóa đại diện không mơ hồ, hoặc dùng một kiểu khóa riêng mô tả thiếu dữ liệu.

Không thay null thành chuỗi rỗng một cách tự động nếu chuỗi rỗng cũng là giá trị hợp lệ trong nghiệp vụ.

## 12. So sánh với `toMap` và `Map.copyOf` để không áp nhầm quy tắc

**`Collectors.toUnmodifiableMap`** được bổ sung Java 10, trả về map không sửa được và yêu cầu không có khóa/giá trị null.

**`Collectors.toMap`** tạo map theo những overload có hợp đồng riêng; các overload không cung cấp `mapFactory` không cam kết kiểu triển khai map cụ thể. Không nên dựa vào việc bản JDK hiện tại tình cờ dùng một implementation hỗ trợ khóa null để kết luận mọi `toMap` đều cho null. Khi cần chính sách null cụ thể, hãy đọc hợp đồng API bạn thực sự sử dụng và lựa chọn/thiết kế map đích phù hợp.

**`Map.copyOf(existingMap)`** cũng từ Java 10 và cho kết quả không sửa được không chứa null, nhưng nhận **một map đã có**, thay vì nhận stream và hai mapper. Nếu map nguồn có khóa hoặc giá trị null, `Map.copyOf` ném `NullPointerException`. Nó không thay thế được việc xử lý mapper và duplicate trong `toUnmodifiableMap`.

Ví dụ:

~~~java
var built = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                java.util.function.Function.identity(),
                String::length));

// built: Map<String, Integer>, không sửa được, không null.
System.out.println(built.get("A")); // 1
~~~

Nếu cần bản map **có thể sửa**, hãy tạo một `HashMap` hoặc loại map phù hợp **một cách có chủ đích**, và xử lý nullable key/value theo hợp đồng của loại đó. Không gọi `put` trên kết quả `toUnmodifiableMap` với mong đợi nó có thể sửa.

## 13. Những lỗi phổ biến khi debug

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| NPE ngay tại `Collectors.toUnmodifiableMap(...)` | `keyMapper`, `valueMapper` hoặc `mergeFunction` được truyền **null** | Kiểm tra tham chiếu hàm trước khi xây collector |
| NPE khi stream chạy đến một bản ghi | Mapper hợp lệ trả về khóa hoặc giá trị `null`, hoặc chính mapper dereference một input null | Kiểm tra dữ liệu và kết quả từng mapper; đặt thông báo lỗi rõ |
| `IllegalStateException` | Hai phần tử tạo **khóa trùng**, đang dùng overload hai đối số | Kiểm tra unique key hoặc dùng overload có merge policy |
| Không thấy NPE khi merge trả null | Theo `Map.merge`, kết quả null có thể **xóa ánh xạ** | Phân biệt với valueMapper trả null; đánh giá chính sách nghiệp vụ |
| `UnsupportedOperationException` sau khi thu thập | Cố thay đổi map không sửa được bằng `put`/`remove`/... | Tạo map mutable mới nếu cần cập nhật, hoặc xây map trước khi công bố |
| Kết quả khác do cách in map | Map không có cam kết thứ tự iteration | Kiểm tra `get`, `size`, `containsKey` thay vì thứ tự `toString()` |

Trong quá trình chẩn đoán, hãy tách các bước: **tạo collector → ánh xạ từng phần tử thành khóa/giá trị → giải quyết khóa trùng → hoàn tất map không sửa được**. Mỗi bước có một nhóm lỗi đặc trưng.

**Không dùng thông điệp NPE làm hợp đồng:** loại ngoại lệ và điều kiện gây lỗi được API quy định, nhưng text chi tiết trong thông báo hoặc vị trí khung stack trace có thể khác giữa JDK.

## 14. Bài tập tự kiểm tra

### Câu 1 — nguồn stream rỗng có miễn trừ mapper null?

~~~java
// Đoạn lỗi cố ý:
var collector = Collectors.<String, String, Integer>
        toUnmodifiableMap(null, String::length);
~~~

**Đáp án:** Không. `keyMapper` là `null` nên NPE xảy ra ngay khi xây collector, kể cả định dùng nó cho stream rỗng.

### Câu 2 — mapper trả null thì làm sao?

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.equals("B") ? null : s,
                String::length));
~~~

**Đáp án:** NPE khi collect vì khóa được ánh xạ từ `"B"` là null. Thay bằng khóa hợp lệ, lọc bản ghi trước đó, hoặc chủ động từ chối dữ liệu có thiếu khóa.

### Câu 3 — trùng khóa không có merge function?

~~~java
var result = java.util.stream.Stream.of("A:2", "A:3")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2))));
~~~

**Đáp án:** `IllegalStateException` do hai khóa `"A"` bằng nhau. Không phải lỗi do null.

### Câu 4 — merge function trả null có lưu value null?

~~~java
var result = java.util.stream.Stream.of("A:2", "A:3")
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> s.substring(0, 1),
                s -> Integer.parseInt(s.substring(2)),
                (first, second) -> null));

System.out.println(result.size());
~~~

**Đáp án:** In `0` trong ví dụ. Theo ngữ nghĩa `Map.merge`, ánh xạ `"A"` bị loại; không lưu `"A" -> null`.

### Câu 5 — stream có phần tử null có luôn bị từ chối?

~~~java
var result = java.util.stream.Stream.<String>of(null)
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                s -> "MISSING", s -> 0));

System.out.println(result.get("MISSING"));
~~~

**Đáp án:** In `0`; cả hai mapper đều tạo đầu ra khác null. Nếu mapper dereference tham chiếu null hoặc trả về khóa/giá trị null, mới có thể phát sinh NPE trong trường hợp này.

## 15. Ghi nhớ

- `Collectors.toUnmodifiableMap` (**Java 10+**) tạo map **không sửa được, không có khóa hoặc giá trị `null`**.
- **`keyMapper` và `valueMapper` phải khác `null`**. Với overload ba đối số, **`mergeFunction` cũng phải khác `null`**; vi phạm gây NPE khi tạo collector.
- **Kết quả `keyMapper` hoặc `valueMapper` trả null** gây NPE trong quá trình thu thập.
- **Khóa trùng** ở overload hai đối số gây **`IllegalStateException`**; overload ba đối số giải quyết bằng chính sách merge.
- **`mergeFunction` hợp lệ trả null** không lưu giá trị null: theo `Map.merge`, ánh xạ liên quan bị xóa.
- **Phần tử stream `null` không đồng nghĩa ngay với khóa/value null**; mapper có thể xử lý nó thành đầu ra hợp lệ nếu nghiệp vụ cho phép.
- Để xử lý dữ liệu thiếu, **kiểm tra, lọc hoặc chuyển đổi có chủ đích** trước khi thu thập; không dựa vào việc collector tự bỏ null.

### Tài liệu tham khảo chính thức

- [Java SE 26 — `Collectors.toUnmodifiableMap(Function, Function)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function)): cấm null key/value, cấm tham số mapper null, duplicate gây `IllegalStateException`.
- [Java SE 26 — `Collectors.toUnmodifiableMap(Function, Function, BinaryOperator)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function,java.util.function.BinaryOperator)): mergeFunction khác null, giải quyết duplicate theo `Map.merge`.
- [Java SE 26 — `Map.merge`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): khi remapping function trả null, xóa ánh xạ.
