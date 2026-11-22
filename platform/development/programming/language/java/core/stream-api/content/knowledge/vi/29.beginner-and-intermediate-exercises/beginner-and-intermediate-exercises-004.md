# Phân biệt kết quả giữa filter, takeWhile và dropWhile

## 1. Mục tiêu bài học và bài tập

Trong chương **Bài tập nền tảng và trung cấp** của **JAVA_STREAM_API**, người học đã biết xây dựng pipeline khai báo bằng `filter`, `map`, `reduce` và `collect`. Bài này tập trung vào một khác biệt rất dễ gây lỗi: cùng một `Predicate` nhưng `filter`, `takeWhile` và `dropWhile` có thể tạo ra **ba tập kết quả khác nhau**.

Sau khi hoàn thành, bạn có thể:

- Dự đoán chính xác kết quả của ba operation trên **Stream có encounter order**.
- Xác định **tiền tố liên tiếp** thỏa điều kiện và **hậu tố** bắt đầu từ phần tử không thỏa đầu tiên.
- Giải thích khi nào `filter` và `takeWhile` trùng kết quả, và khi nào hoàn toàn khác nhau.
- Chọn operation phù hợp cho bài toán cảm biến, sự kiện, nhật ký, dữ liệu thời gian.
- Xử lý nguồn rỗng, phần tử `null`, điều kiện luôn đúng/luôn sai và nguồn vô hạn.
- Hiểu ràng buộc của `unordered()` và chi phí phối hợp trong parallel stream.
- Viết kiểm thử dựa trên **kết quả**, không dựa vào số lần callback được gọi.

Các ví dụ sử dụng **Java 17+**. `filter` có từ Java 8; `takeWhile` và `dropWhile` được bổ sung từ **Java 9**, áp dụng cả cho `Stream<T>` và các primitive stream như `IntStream`, `LongStream`, `DoubleStream`.

### Bảng nhớ nhanh

| Operation | Xử lý trên Stream có thứ tự | Khi gặp phần tử đầu tiên không thỏa `P` | Kết quả |
| --- | --- | --- | --- |
| `filter(P)` | Kiểm tra từng phần tử của toàn nguồn | Vẫn tiếp tục xét các phần tử sau | **Mọi phần tử** thỏa `P` |
| `takeWhile(P)` | Lấy tiền tố liên tiếp thỏa `P` | Dừng lấy phần tử | **Tiền tố thỏa `P`** |
| `dropWhile(P)` | Bỏ tiền tố liên tiếp thỏa `P` | Bắt đầu giữ phần tử này và toàn bộ phần sau | **Hậu tố còn lại** |

**Điểm cần nhớ:** Khi `dropWhile` đã gặp phần tử đầu tiên không thỏa `P`, nó **không tiếp tục lọc bằng `P`**. Những phần tử ở hậu tố có thể đúng hoặc sai theo predicate, nhưng đều được giữ.

## 2. Mô hình tư duy: một nguồn, một predicate, ba đáp án

Xét nguồn có thứ tự:

~~~text
Nguồn:  [2, 4, 7, 3, 8, 1]
P(x):    x < 5

Từng phần tử:
         2✓  4✓  7✗  3✓  8✗  1✓
                │
                └── Ranh giới đầu tiên không thỏa P

filter(P):     [2, 4, 3, 1]
takeWhile(P):  [2, 4]
dropWhile(P):  [7, 3, 8, 1]
~~~

`filter` chọn tất cả số nhỏ hơn 5 dù chúng nằm ở đầu, giữa hay cuối nguồn. `takeWhile` chỉ chọn `2` và `4` vì `7` là điểm phá vỡ chuỗi liên tiếp. `dropWhile` bỏ đúng tiền tố `[2,4]` rồi giữ cả `7`, `3`, `8`, `1`.

### Ví dụ hoàn chỉnh chạy được

~~~java
import java.util.Arrays;
import java.util.List;

public class CompareThreeOperations {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 7, 3, 8, 1);

        List<Integer> filtered = values.stream()
            .filter(n -> n < 5)
            .toList();

        List<Integer> taken = values.stream()
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> dropped = values.stream()
            .dropWhile(n -> n < 5)
            .toList();

        System.out.println(filtered); // [2, 4, 3, 1]
        System.out.println(taken);     // [2, 4]
        System.out.println(dropped);   // [7, 3, 8, 1]
    }
}
~~~

Ta tạo một Stream mới ở **mỗi** phép toán. Stream được thiết kế để tiêu thụ một lần; không tạo một biến Stream rồi gọi ba terminal operation trên nó.

### Câu hỏi suy nghĩ trước khi làm bài

Nếu thay `n < 5` bằng `n >= 5` thì `takeWhile` trả gì? Vì phần tử đầu tiên là `2` và không thỏa điều kiện, kết quả là **danh sách rỗng**. Còn `dropWhile` sẽ giữ **toàn bộ nguồn**.

## 3. Bài tập 1 — Dự đoán kết quả trên dữ liệu chưa sắp xếp

**Mức độ:** Cơ bản.

**Đề bài:** Với dãy `[1, 3, 6, 2, 7, 4]` và điều kiện `n < 5`, hãy viết ra kết quả của `filter`, `takeWhile`, `dropWhile` trước khi chạy chương trình.

**Đáp án:**

| Operation | Kết quả | Giải thích |
| --- | --- | --- |
| `filter(n -> n < 5)` | `[1, 3, 2, 4]` | Chọn tất cả số nhỏ hơn 5. |
| `takeWhile(n -> n < 5)` | `[1, 3]` | Dừng ở `6`, phần tử đầu tiên không nhỏ hơn 5. |
| `dropWhile(n -> n < 5)` | `[6, 2, 7, 4]` | Chỉ bỏ tiền tố `[1,3]`. |

**Lời giải Java:**

~~~java
import java.util.List;

public class Exercise01 {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 3, 6, 2, 7, 4);

        System.out.println(numbers.stream()
            .filter(n -> n < 5).toList());
        // [1, 3, 2, 4]

        System.out.println(numbers.stream()
            .takeWhile(n -> n < 5).toList());
        // [1, 3]

        System.out.println(numbers.stream()
            .dropWhile(n -> n < 5).toList());
        // [6, 2, 7, 4]
    }
}
~~~

**Lỗi thường gặp:** cho rằng `dropWhile(n -> n < 5)` tương đương `filter(n -> n >= 5)`. Với dãy này, filter theo phủ định chỉ cho `[6,7]`, còn `dropWhile` giữ cả `2` và `4` ở hậu tố.

## 4. Bài tập 2 — Dữ liệu đã sắp xếp tăng dần

**Mức độ:** Cơ bản.

**Đề bài:** Cho `[1, 2, 2, 4, 5, 7, 9]` đã sắp tăng. Hãy tách các số **nhỏ hơn 5** khỏi các số từ 5 trở lên; so sánh ba operation.

~~~java
import java.util.List;

public class Exercise02 {
    public static void main(String[] args) {
        List<Integer> sorted = List.of(1, 2, 2, 4, 5, 7, 9);

        List<Integer> allSmall = sorted.stream()
            .filter(n -> n < 5)
            .toList();

        List<Integer> prefix = sorted.stream()
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> suffix = sorted.stream()
            .dropWhile(n -> n < 5)
            .toList();

        System.out.println(allSmall); // [1, 2, 2, 4]
        System.out.println(prefix);   // [1, 2, 2, 4]
        System.out.println(suffix);   // [5, 7, 9]
    }
}
~~~

**Tại sao `filter` và `takeWhile` bằng nhau trong trường hợp này?**

Vì dữ liệu được sắp tăng và điều kiện `n < 5` có tính **đơn điệu theo thứ tự**: một khi đã thấy số `>= 5`, không thể xuất hiện số nhỏ hơn 5 ở phía sau. Tất cả phần tử thỏa predicate tạo thành **một tiền tố**.

Điều kiện tổng quát để `filter(P)` và `takeWhile(P)` cho cùng kết quả trên Stream ordered là: **không có phần tử thỏa `P` xuất hiện sau phần tử đầu tiên không thỏa `P`**.

Tương tự, nếu mọi phần tử không thỏa `P` đều nằm trong một hậu tố, `dropWhile(P)` tương đương `filter(P.negate())` trên dãy đó. Đây là tính chất của **dữ liệu và predicate**, không phải sự đồng nghĩa của API.

### Cẩn thận với predicate khác

Một danh sách tăng dần **không bảo đảm** mọi predicate đều đơn điệu. Ví dụ `n % 2 == 0` có thể đúng, sai, rồi đúng lại dù danh sách đã được sắp:

~~~text
Nguồn: [2, 3, 4, 5, 6]
P: số chẵn

filter       → [2, 4, 6]
takeWhile    → [2]
dropWhile    → [3, 4, 5, 6]
~~~

Chỉ được thay `filter` bằng `takeWhile` khi hiểu rõ **quy luật thứ tự của dữ liệu so với predicate**.

## 5. Bài tập 3 — Phần tử đầu tiên đã sai điều kiện

**Mức độ:** Cơ bản.

**Đề bài:** Dự đoán kết quả khi nguồn là `[9, 1, 2, 3]` và `P(n) = n < 5`.

~~~java
import java.util.List;

List<Integer> numbers = List.of(9, 1, 2, 3);

System.out.println(numbers.stream()
    .filter(n -> n < 5).toList()); // [1, 2, 3]

System.out.println(numbers.stream()
    .takeWhile(n -> n < 5).toList()); // []

System.out.println(numbers.stream()
    .dropWhile(n -> n < 5).toList()); // [9, 1, 2, 3]
~~~

**Giải thích:** `takeWhile` không có một phần tử đầu tiên hợp lệ nào để giữ. `dropWhile` không có tiền tố hợp lệ nào cần bỏ, nên trả lại toàn bộ dãy. Trong khi đó, `filter` vẫn thấy các số `1, 2, 3` ở cuối và chọn chúng.

**Bài thử mở rộng:** Nếu chỉ đổi thứ tự nguồn thành `[1,2,3,9]`, `takeWhile` trả `[1,2,3]`, còn `dropWhile` trả `[9]`. Cùng tập giá trị nhưng **encounter order khác** đã làm kết quả khác.

## 6. Bài tập 4 — Điều kiện luôn đúng, luôn sai và nguồn rỗng

**Mức độ:** Cơ bản.

**Đề bài:** Lập bảng kết quả của ba operation khi predicate luôn trả `true`, luôn trả `false`, hoặc Stream không có phần tử.

| Nguồn | Predicate | `filter` | `takeWhile` | `dropWhile` |
| --- | --- | --- | --- | --- |
| `[1,2,3]` | `n -> true` | `[1,2,3]` | `[1,2,3]` | `[]` |
| `[1,2,3]` | `n -> false` | `[]` | `[]` | `[1,2,3]` |
| `[]` | Bất kỳ predicate hợp lệ | `[]` | `[]` | `[]` |

**Lời giải kiểm chứng:**

~~~java
import java.util.List;

public class Exercise04 {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3);

        System.out.println(source.stream()
            .takeWhile(n -> true).toList()); // [1, 2, 3]

        System.out.println(source.stream()
            .dropWhile(n -> true).toList()); // []

        System.out.println(source.stream()
            .takeWhile(n -> false).toList()); // []

        System.out.println(source.stream()
            .dropWhile(n -> false).toList()); // [1, 2, 3]

        System.out.println(List.<Integer>of().stream()
            .filter(n -> n > 0).toList()); // []

        System.out.println(List.<Integer>of().stream()
            .takeWhile(n -> n > 0).toList()); // []

        System.out.println(List.<Integer>of().stream()
            .dropWhile(n -> n > 0).toList()); // []
    }
}
~~~

Dùng `List.<Integer>of()` giúp kiểu generic của Stream rỗng rõ ràng. Nếu pipeline có terminal `findFirst()` sau đó, mọi trường hợp không còn phần tử sẽ trả `Optional.empty()`.

## 7. Bài tập 5 — Phân định ranh giới bằng <= và <

**Mức độ:** Cơ bản → Trung cấp.

**Đề bài:** Với dãy tăng `[10,20,30,40,50]`, lấy tất cả phần tử **trước** mốc 30 rồi lấy tất cả phần tử **từ** mốc 30 trở đi. Sửa predicate nếu muốn đưa mốc 30 vào nhóm đầu.

**Lời giải:**

~~~java
import java.util.List;

public class BoundaryExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(10, 20, 30, 40, 50);

        List<Integer> before30 = values.stream()
            .takeWhile(n -> n < 30)
            .toList();

        List<Integer> from30 = values.stream()
            .dropWhile(n -> n < 30)
            .toList();

        List<Integer> through30 = values.stream()
            .takeWhile(n -> n <= 30)
            .toList();

        System.out.println(before30);  // [10, 20]
        System.out.println(from30);    // [30, 40, 50]
        System.out.println(through30); // [10, 20, 30]
    }
}
~~~

Điểm ranh giới **đầu tiên không thỏa predicate** nằm trong kết quả của `dropWhile`, chứ không phải bị bỏ. Với `n < 30`, số 30 chính là phần tử đầu hậu tố.

### Kiểm tra khi có giá trị trùng ranh giới

~~~text
Nguồn: [10, 20, 30, 30, 40]

takeWhile(n < 30) → [10, 20]
dropWhile(n < 30) → [30, 30, 40]

takeWhile(n <= 30) → [10, 20, 30, 30]
dropWhile(n <= 30) → [40]
~~~

**Câu hỏi:** Vì sao `dropWhile(n -> n < 30)` giữ cả hai số 30? Vì một khi gặp số 30 đầu tiên không thỏa, nó giữ **mọi phần tử còn lại** chứ không tiếp tục đánh giá điều kiện để loại từng phần tử.

## 8. Bài tập 6 — Giữ kết quả theo thứ tự đọc sự kiện

**Mức độ:** Trung cấp.

**Đề bài:** Một hệ thống ghi nhật ký các trạng thái theo đúng thứ tự thời gian. Ta muốn biết:

1. Những sự kiện **trước lỗi đầu tiên**.
2. Những sự kiện **từ lỗi đầu tiên trở về sau**.
3. Mọi sự kiện **không phải lỗi** trong toàn bộ nhật ký.

Ba câu hỏi này khác nhau; hãy chọn operation tương ứng.

**Lời giải:**

~~~java
import java.util.List;

public class EventLogExercise {
    record Event(int sequence, String level, String message) {}

    public static void main(String[] args) {
        List<Event> log = List.of(
            new Event(1, "INFO",  "Bắt đầu"),
            new Event(2, "WARN",  "Chờ tài nguyên"),
            new Event(3, "ERROR", "Mất kết nối"),
            new Event(4, "INFO",  "Đang thử lại"),
            new Event(5, "ERROR", "Hết lượt thử")
        );

        List<Event> beforeFirstError = log.stream()
            .takeWhile(e -> !"ERROR".equals(e.level()))
            .toList();

        List<Event> fromFirstError = log.stream()
            .dropWhile(e -> !"ERROR".equals(e.level()))
            .toList();

        List<Event> allNonErrors = log.stream()
            .filter(e -> !"ERROR".equals(e.level()))
            .toList();

        System.out.println(beforeFirstError.stream()
            .map(Event::sequence).toList()); // [1, 2]

        System.out.println(fromFirstError.stream()
            .map(Event::sequence).toList()); // [3, 4, 5]

        System.out.println(allNonErrors.stream()
            .map(Event::sequence).toList()); // [1, 2, 4]
    }
}
~~~

**Giải thích:** `takeWhile` trả **tiền tố** không có lỗi. `dropWhile` trả **hậu tố** từ lỗi đầu tiên; hậu tố có thể chứa các sự kiện INFO/WARN sau lỗi. `filter` trả tất cả sự kiện không lỗi, kể cả sự kiện ở **sau lỗi**.

Đây là một ví dụ điển hình mà dùng `filter` thay `takeWhile` sẽ phá ý nghĩa nghiệp vụ: câu hỏi “trước lỗi đầu tiên” không phải “mọi sự kiện không lỗi”.

### Nếu log không được sắp theo thời gian?

`takeWhile` và `dropWhile` dựa trên **encounter order của Stream**, không tự kiểm tra timestamp hoặc trường `sequence`. Nếu dữ liệu đến không đúng thứ tự mà yêu cầu nghiệp vụ là “trước lỗi theo thời gian”, hãy sắp xếp theo khóa thời gian đủ rõ trước khi tìm ranh giới:

~~~java
List<Event> chronological = log.stream()
    .sorted(java.util.Comparator.comparingInt(Event::sequence))
    .toList();

List<Event> beforeError = chronological.stream()
    .takeWhile(e -> !"ERROR".equals(e.level()))
    .toList();
~~~

Sắp xếp có thể tốn thêm thời gian và bộ nhớ. Không thêm `sorted()` chỉ để làm một bài toán vốn chỉ cần `filter`.

## 9. Bài tập 7 — Đọc chuỗi phép đo trước và sau ngưỡng

**Mức độ:** Trung cấp.

**Đề bài:** Một thiết bị gửi dãy nhiệt độ theo **thứ tự thời gian**: `[65,68,72,82,75,90]`. Ngưỡng cảnh báo là 80. Hãy lấy:

- Tất cả phép đo dưới ngưỡng trong toàn bộ phiên.
- Những phép đo liên tiếp **trước cảnh báo đầu tiên**.
- Những phép đo **từ cảnh báo đầu tiên** tới cuối phiên.

~~~java
import java.util.List;

public class TemperatureExercise {
    public static void main(String[] args) {
        List<Integer> temperatures =
            List.of(65, 68, 72, 82, 75, 90);

        List<Integer> safeReadings = temperatures.stream()
            .filter(t -> t < 80)
            .toList();

        List<Integer> beforeAlarm = temperatures.stream()
            .takeWhile(t -> t < 80)
            .toList();

        List<Integer> fromAlarm = temperatures.stream()
            .dropWhile(t -> t < 80)
            .toList();

        System.out.println(safeReadings); // [65, 68, 72, 75]
        System.out.println(beforeAlarm);  // [65, 68, 72]
        System.out.println(fromAlarm);    // [82, 75, 90]
    }
}
~~~

Sau khi vượt ngưỡng tại 82, nhiệt độ trở về 75 nhưng **vẫn thuộc hậu tố** của `dropWhile`. Nếu muốn **chỉ** các số đo từ 80 trở lên, dùng `filter(t -> t >= 80)`, kết quả `[82,90]`.

### Bài mở rộng

Viết hàm trả về chỉ số (hoặc timestamp) của cảnh báo đầu tiên. Nếu dữ liệu không chứa cảnh báo, hãy giữ trạng thái **vắng mặt**, ví dụ bằng `OptionalInt` hoặc `Optional<Reading>`, thay vì trả một timestamp giả dễ gây hiểu nhầm.

## 10. Bài tập 8 — Ghép operation: thứ tự các bước quan trọng

**Mức độ:** Trung cấp.

**Đề bài:** Xét `[2,5,4,1,6]`. So sánh hai pipeline:

- Lọc số chẵn, **sau đó** lấy các số nhỏ hơn 5 cho đến phần tử không phù hợp đầu tiên.
- Lấy tiền tố nhỏ hơn 5, **sau đó** lọc số chẵn.

~~~java
import java.util.List;

public class CompositionExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 5, 4, 1, 6);

        List<Integer> filterThenTake = values.stream()
            .filter(n -> n % 2 == 0)
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> takeThenFilter = values.stream()
            .takeWhile(n -> n < 5)
            .filter(n -> n % 2 == 0)
            .toList();

        System.out.println(filterThenTake); // [2, 4]
        System.out.println(takeThenFilter); // [2]
    }
}
~~~

**Giải thích chi tiết:**

~~~text
Nguồn ban đầu:               [2, 5, 4, 1, 6]

filter(số chẵn):             [2, 4, 6]
takeWhile(n < 5):            [2, 4]

takeWhile(n < 5) trước:      [2]
filter(số chẵn) sau:         [2]
~~~

Việc loại số 5 ở bước `filter` trước khiến `takeWhile` **không còn thấy điểm ranh giới này** và tiếp tục lấy được số 4. Khi đặt `takeWhile` trước, số 5 kết thúc tiền tố, nên số 4 ở sau không được xét để giữ.

**Kết luận:** Không tùy tiện đổi chỗ `filter` với `takeWhile` hay `dropWhile`. Chúng không phải các phép biến đổi có thể hoán đổi tự do như một số bộ lọc độc lập.

## 11. Bài tập 9 — Nguồn rỗng, phần tử null và ranh giới null

**Mức độ:** Trung cấp.

**Đề bài:** Nguồn `List<Integer>` có thể chứa `null`. Với `[1,2,null,3,4]`, quyết định hai chính sách khác nhau:

- **Chính sách A:** gặp `null` coi như **kết thúc đoạn hợp lệ**.
- **Chính sách B:** bỏ `null` rồi xét các giá trị số như bình thường.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class NullBoundaryExercise {
    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(1, 2, null, 3, 4);

        // A: null là ranh giới.
        List<Integer> beforeGap = values.stream()
            .takeWhile(n -> n != null && n < 4)
            .toList();

        List<Integer> fromGap = values.stream()
            .dropWhile(n -> n != null && n < 4)
            .toList();

        // B: bỏ null trước khi áp predicate.
        List<Integer> afterCleaning = values.stream()
            .filter(Objects::nonNull)
            .takeWhile(n -> n < 4)
            .toList();

        System.out.println(beforeGap);    // [1, 2]
        System.out.println(fromGap);      // [null, 3, 4]
        System.out.println(afterCleaning); // [1, 2, 3]
    }
}
~~~

**Chú ý:**

- `n -> n < 4` **tự động unbox** `Integer` thành `int`; nếu `n == null` thì có thể ném `NullPointerException`.
- Khi `null` là ranh giới, predicate phải kiểm tra `n != null` trước phép so sánh.
- Khi muốn bỏ `null` khỏi nguồn, có thể `filter(Objects::nonNull)` trước khi `takeWhile`.
- `Stream.toList()` có thể chứa phần tử null nhưng kết quả không sửa đổi được; `Collectors.toUnmodifiableList()` cấm null.

Hai chính sách A và B **không tương đương**. Hãy chọn dựa trên dữ liệu thiếu có nghĩa là “đứt đoạn” hay chỉ là “bản ghi không cần xét”.

### Nguồn tham chiếu null khác với phần tử null

~~~java
List<Integer> source = null;

// Không được gọi source.stream().
List<Integer> safeSource =
    java.util.Optional.ofNullable(source).orElseGet(List::of);

System.out.println(safeSource.stream()
    .takeWhile(n -> n < 4).toList()); // []
~~~

Chỉ dùng chính sách “nguồn null = nguồn rỗng” khi hợp đồng nghiệp vụ cho phép. Nếu nguồn bắt buộc có, hãy dùng `Objects.requireNonNull(source, "...")` để báo lỗi rõ ràng.

## 12. Bài tập 10 — Stream vô hạn và nguy cơ không kết thúc

**Mức độ:** Trung cấp.

**Đề bài:** Một nguồn số nguyên liên tục bắt đầu từ 0. Hãy tạo:

1. Năm số đầu tiên nhỏ hơn 5.
2. Ba số liên tiếp bắt đầu từ 5.
3. Giải thích vì sao không thể thay mọi trường hợp bằng `filter` trên nguồn vô hạn.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class InfiniteStreamExercise {
    public static void main(String[] args) {
        int[] prefix = IntStream.iterate(0, n -> n + 1)
            .takeWhile(n -> n < 5)
            .toArray();

        int[] suffixStart = IntStream.iterate(0, n -> n + 1)
            .dropWhile(n -> n < 5)
            .limit(3)
            .toArray();

        System.out.println(Arrays.toString(prefix)); // [0, 1, 2, 3, 4]
        System.out.println(Arrays.toString(suffixStart)); // [5, 6, 7]
    }
}
~~~

Ở đây `takeWhile(n < 5)` có thể kết thúc vì nguồn cuối cùng phát một số không nhỏ hơn 5. `dropWhile(n < 5)` bỏ các giá trị 0–4; `limit(3)` ở phía sau giúp terminal kết thúc sau ba kết quả được giữ.

### Không chạy những ví dụ sau trên nguồn vô hạn không giới hạn

~~~java
// Tránh chạy: không kết thúc vì filter liên tục đọc nguồn
// để tìm thêm các phần tử thỏa n < 5, sau khi đã qua ranh giới.
// IntStream.iterate(0, n -> n + 1)
//     .filter(n -> n < 5)
//     .toArray();

// Tránh chạy: hậu tố sau ranh giới là vô hạn.
// IntStream.iterate(0, n -> n + 1)
//     .dropWhile(n -> n < 5)
//     .toArray();
~~~

`filter` không có quyền tự dừng toàn bộ pipeline vì gặp một phần tử sai điều kiện; các phần tử sau đó **về lý thuyết có thể thỏa lại**. `takeWhile` có thể dừng ở điểm phá vỡ tiền tố đối với nguồn có thứ tự. `dropWhile` không cắt hậu tố, nên cần một terminal hoặc operation khác có khả năng giới hạn kết quả.

**Ngoại lệ cần hiểu:** `filter(P).limit(k)` vẫn có thể kết thúc nếu nguồn cuối cùng cho **đủ k phần tử** thỏa `P`. Không đánh đồng “filter trên nguồn vô hạn” với “mọi pipeline chứa filter đều vô hạn”.

### Nếu predicate không bao giờ sai?

`takeWhile(n -> true)` trên một nguồn vô hạn **không thể** tự tạo kết quả `toList()` hữu hạn. Điều kiện dừng phải tồn tại trong dữ liệu hoặc trong các operation khác.

## 13. Bài tập 11 — Song song và unordered: không còn một tiền tố xác định

**Mức độ:** Trung cấp.

**Đề bài:** Chạy ba operation trên `IntStream.rangeClosed(1,8)` ở chế độ song song. Sau đó thêm `unordered()` và giải thích vì sao **không được viết kiểm thử dựa vào một đầu ra cụ thể** cho `takeWhile`/`dropWhile` khi nguồn không còn encounter order.

### 13.1. Ordered parallel stream

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class OrderedParallelExercise {
    public static void main(String[] args) {
        int[] filtered = IntStream.rangeClosed(1, 8)
            .parallel()
            .filter(n -> n < 5)
            .toArray();

        int[] taken = IntStream.rangeClosed(1, 8)
            .parallel()
            .takeWhile(n -> n < 5)
            .toArray();

        int[] dropped = IntStream.rangeClosed(1, 8)
            .parallel()
            .dropWhile(n -> n < 5)
            .toArray();

        System.out.println(Arrays.toString(filtered)); // [1, 2, 3, 4]
        System.out.println(Arrays.toString(taken)); // [1, 2, 3, 4]
        System.out.println(Arrays.toString(dropped)); // [5, 6, 7, 8]
    }
}
~~~

`parallel()` **không tự hủy encounter order**. `IntStream.rangeClosed` có encounter order xác định; các operation vẫn phải duy trì ngữ nghĩa ordered dù các nhánh được thực hiện trên nhiều thread.

### 13.2. Unordered stream

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class UnorderedWhileExercise {
    public static void main(String[] args) {
        int[] taken = IntStream.rangeClosed(1, 8)
            .parallel()
            .unordered()
            .takeWhile(n -> n < 5)
            .toArray();

        int[] dropped = IntStream.rangeClosed(1, 8)
            .parallel()
            .unordered()
            .dropWhile(n -> n < 5)
            .toArray();

        System.out.println(Arrays.toString(taken));
        System.out.println(Arrays.toString(dropped));
        // Không dựa vào hai mảng có nội dung/thứ tự cố định.
    }
}
~~~

Trên **unordered stream**, Java cho phép:

- `takeWhile(P)` lấy **bất kỳ tập con** nào của các phần tử thỏa `P`. Không bảo đảm lấy toàn bộ `[1,2,3,4]`.
- `dropWhile(P)` bỏ **bất kỳ tập con** nào của các phần tử thỏa `P`. Các phần tử không thỏa `P` vẫn thuộc kết quả; một số phần tử thỏa `P` cũng có thể còn lại.
- `filter(P)` vẫn có nhiệm vụ giữ **tất cả phần tử thỏa `P`** về mặt tập giá trị, dù thứ tự duyệt có thể không xác định.

`unordered()` **không phải shuffle**. Việc một lần chạy tạo cùng kết quả như nguồn ordered không tạo ra bảo đảm cho những lần sau.

### 13.3. Những bất biến có thể kiểm thử

Với `taken` sau `takeWhile(n < 5)`, ta chỉ được dựa vào mọi phần tử đều nhỏ hơn 5; số phần tử có thể thay đổi. Với `dropped`, phải giữ mọi phần tử từ 5 đến 8, nhưng có thể còn các số từ 1 đến 4.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] taken = IntStream.rangeClosed(1, 8)
    .parallel().unordered()
    .takeWhile(n -> n < 5)
    .toArray();

boolean allTakenMatch = Arrays.stream(taken)
    .allMatch(n -> n < 5);

if (!allTakenMatch) {
    throw new AssertionError("takeWhile phát phần tử không hợp lệ");
}

int[] dropped = IntStream.rangeClosed(1, 8)
    .parallel().unordered()
    .dropWhile(n -> n < 5)
    .toArray();

for (int mustRemain = 5; mustRemain <= 8; mustRemain++) {
    final int value = mustRemain;
    if (Arrays.stream(dropped).noneMatch(n -> n == value)) {
        throw new AssertionError("dropWhile làm mất " + value);
    }
}
~~~

Kết quả này chỉ kiểm tra những bất biến được hợp đồng đảm bảo; không suy ra tốc độ hay lịch thread. Nếu bài toán là **giữ tiền tố của dữ liệu thời gian**, phải giữ encounter order và không dùng `unordered()`.

## 14. Bài tập 12 — Ghép with limit, skip và findFirst

**Mức độ:** Trung cấp.

**Đề bài:** Cho dãy `[1,2,3,8,4,9]`. Hãy so sánh việc lấy hai phần tử đầu tiên bằng `limit` và việc lấy tiền tố theo điều kiện. Sau đó tìm **phần tử đầu tiên không thỏa `n < 5`**.

~~~java
import java.util.List;
import java.util.Optional;

public class TerminalCompositionExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 8, 4, 9);

        List<Integer> firstTwo = values.stream()
            .limit(2)
            .toList();

        List<Integer> prefix = values.stream()
            .takeWhile(n -> n < 5)
            .toList();

        Optional<Integer> firstFailure = values.stream()
            .dropWhile(n -> n < 5)
            .findFirst();

        List<Integer> afterBoundary = values.stream()
            .dropWhile(n -> n < 5)
            .skip(1)
            .toList();

        System.out.println(firstTwo);      // [1, 2]
        System.out.println(prefix);        // [1, 2, 3]
        System.out.println(firstFailure);  // Optional[8]
        System.out.println(afterBoundary); // [4, 9]
    }
}
~~~

- `limit(k)` giới hạn theo **số lượng**, không theo một predicate.
- `takeWhile(P)` giới hạn theo **ranh giới đầu tiên** không thỏa `P`.
- `dropWhile(P).findFirst()` lấy phần tử **phá vỡ tiền tố** nếu có.
- `dropWhile(P).skip(1)` bỏ thêm chính phần tử phá vỡ tiền tố, giữ những phần tử sau nó.

Nếu mọi phần tử đều thỏa `P`, `dropWhile(P).findFirst()` trả `Optional.empty()`. Đừng gọi `get()` khi không có kết quả; dùng `orElse`, `orElseGet` hoặc `orElseThrow` tùy chính sách nghiệp vụ.

### Không nhầm với filter tìm mọi phần tử sai

~~~java
List<Integer> allFailures = values.stream()
    .filter(n -> n >= 5)
    .toList();

System.out.println(allFailures); // [8, 9]
~~~

`filter(n -> n >= 5)` trả **mọi** số vượt ngưỡng, không phải **số đầu tiên vượt ngưỡng cùng tất cả phần tử sau nó**.

## 15. Bài tập tổng hợp — Phân tích phiên kiểm thử đến sự cố đầu tiên

**Mức độ:** Trung cấp.

**Tình huống:** Một hệ thống kiểm thử ghi lại những bước chạy theo đúng thứ tự. Mỗi bản ghi có `sequence`, `durationMs` và `passed`. Nhóm vận hành cần:

1. Danh sách các bước **đã qua** ở bất kỳ vị trí nào.
2. Danh sách các bước **liên tiếp đã qua trước lỗi đầu tiên**.
3. Danh sách các bước **từ lỗi đầu tiên đến cuối phiên**.
4. Mã (sequence) của **lỗi đầu tiên**, ở dạng `OptionalInt` nếu có thể thiếu.
5. Tổng thời gian của các bước **trước lỗi đầu tiên** bằng `long`.

**Lời giải hoàn chỉnh:**

~~~java
import java.util.List;
import java.util.OptionalInt;

public class SessionAnalysis {
    record Step(int sequence, int durationMs, boolean passed) {}

    record Summary(
        List<Step> allPassed,
        List<Step> passedBeforeFailure,
        List<Step> fromFirstFailure,
        OptionalInt firstFailureSequence,
        long preFailureDurationMs
    ) {}

    static Summary analyze(List<Step> steps) {
        List<Step> allPassed = steps.stream()
            .filter(Step::passed)
            .toList();

        List<Step> prefix = steps.stream()
            .takeWhile(Step::passed)
            .toList();

        List<Step> suffix = steps.stream()
            .dropWhile(Step::passed)
            .toList();

        OptionalInt firstFailure = suffix.stream()
            .mapToInt(Step::sequence)
            .findFirst();

        long duration = prefix.stream()
            .mapToLong(Step::durationMs)
            .sum();

        return new Summary(
            allPassed,
            prefix,
            suffix,
            firstFailure,
            duration
        );
    }

    public static void main(String[] args) {
        List<Step> steps = List.of(
            new Step(1, 120, true),
            new Step(2, 80, true),
            new Step(3, 200, false),
            new Step(4, 50, true),
            new Step(5, 100, false)
        );

        Summary summary = analyze(steps);

        System.out.println(summary.allPassed().stream()
            .map(Step::sequence).toList()); // [1, 2, 4]

        System.out.println(summary.passedBeforeFailure().stream()
            .map(Step::sequence).toList()); // [1, 2]

        System.out.println(summary.fromFirstFailure().stream()
            .map(Step::sequence).toList()); // [3, 4, 5]

        System.out.println(summary.firstFailureSequence());
        // OptionalInt[3]

        System.out.println(summary.preFailureDurationMs()); // 200

        Summary noFailure = analyze(List.of(
            new Step(1, 10, true),
            new Step(2, 15, true)
        ));

        System.out.println(noFailure.firstFailureSequence());
        // OptionalInt.empty

        System.out.println(noFailure.fromFirstFailure());
        // []
    }
}
~~~

**Giải thích:**

- `filter(Step::passed)` giữ cả bước `4`, dù nó diễn ra sau lỗi đầu tiên.
- `takeWhile(Step::passed)` chỉ giữ tiền tố `1,2`.
- `dropWhile(Step::passed)` bắt đầu ở bước `3` và bao gồm cả bước thành công `4` phía sau.
- `firstFailureSequence` là Optional vì phiên có thể **không có lỗi nào**.
- `mapToLong` tính tổng thời lượng ở kiểu `long`, tránh tràn sớm khi cộng `int` trên nhiều bước.

**Lưu ý về kiểu:** `suffix.stream().mapToInt(Step::sequence).findFirst()` trả `OptionalInt`. Không gọi `mapToInt` sau `findFirst()` trên `Stream<Step>`, vì khi đó kết quả đã là `Optional<Step>`, không còn là Stream. Trên nguồn rỗng hoặc phiên không có lỗi, `OptionalInt.empty()` biểu diễn chính xác việc không có sự cố.

### Chính sách dữ liệu đầu vào

Bài giả định:

- Danh sách `steps` không phải null; các phần tử `Step` không null.
- Bản ghi đã nằm theo **thứ tự thực thi**. Nếu có thể lệch thứ tự, phải sắp bằng `sequence` hoặc timestamp rõ ràng trước.
- `durationMs` không âm; nếu có giá trị âm, nên báo lỗi hoặc xử lý theo quy tắc nghiệp vụ trước khi tính tổng.
- Một `Step` có `passed = true` sau lỗi đầu tiên vẫn phải xuất hiện trong hậu tố, vì báo cáo cần phân tích những gì xảy ra **sau sự cố**.

Không sửa `steps` bên trong callback; không dùng `parallel().unordered()` khi báo cáo phụ thuộc thứ tự sự kiện.

### Bài mở rộng

Hãy bổ sung `long totalFailureDurationMs`: tính tổng thời gian của **mọi bước thất bại** qua `filter(step -> !step.passed())` rồi `mapToLong(Step::durationMs).sum()`. Chỉ tiêu đó khác với tổng thời gian của hậu tố, vì hậu tố có thể gồm cả bước đã qua sau sự cố.

## 16. Kiểm thử có hệ thống: không dựa vào log callback

**Mức độ:** Trung cấp.

Một bộ kiểm thử tốt phải kiểm tra kết quả của ba phép toán trong nhiều kịch bản, không đếm số lần predicate được gọi. Stream API có thể tối ưu pipeline; với parallel stream, thời điểm và thứ tự thực thi callback không phải hợp đồng để xây dựng đúng/sai.

Dùng một phương thức kiểm thử thuần Java:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.IntPredicate;
import java.util.stream.IntStream;

public class WhileOperationsChecks {
    static void expect(
        int[] input,
        IntPredicate predicate,
        int[] expectedFilter,
        int[] expectedTake,
        int[] expectedDrop
    ) {
        int[] filtered = Arrays.stream(input)
            .filter(predicate)
            .toArray();

        int[] taken = Arrays.stream(input)
            .takeWhile(predicate)
            .toArray();

        int[] dropped = Arrays.stream(input)
            .dropWhile(predicate)
            .toArray();

        if (!Arrays.equals(filtered, expectedFilter)) {
            throw new AssertionError("filter sai");
        }
        if (!Arrays.equals(taken, expectedTake)) {
            throw new AssertionError("takeWhile sai");
        }
        if (!Arrays.equals(dropped, expectedDrop)) {
            throw new AssertionError("dropWhile sai");
        }

        // Với nguồn ordered, take + drop tái tạo đúng input.
        int[] joined = IntStream.concat(
            IntStream.of(taken),
            IntStream.of(dropped)
        ).toArray();

        if (!Arrays.equals(joined, input)) {
            throw new AssertionError("Mất hoặc lặp phần tử");
        }
    }

    public static void main(String[] args) {
        expect(
            new int[] {2, 4, 7, 3, 8, 1},
            n -> n < 5,
            new int[] {2, 4, 3, 1},
            new int[] {2, 4},
            new int[] {7, 3, 8, 1}
        );

        expect(
            new int[] {1, 2, 3},
            n -> true,
            new int[] {1, 2, 3},
            new int[] {1, 2, 3},
            new int[] {}
        );

        expect(
            new int[] {1, 2, 3},
            n -> false,
            new int[] {},
            new int[] {},
            new int[] {1, 2, 3}
        );

        expect(
            new int[] {},
            n -> n > 0,
            new int[] {},
            new int[] {},
            new int[] {}
        );

        System.out.println("PASS");
    }
}
~~~

### Một bất biến quan trọng của ordered stream

Với cùng một ordered source và cùng predicate thuần, kết quả của `takeWhile(P)` nối với kết quả của `dropWhile(P)` phải khôi phục lại nguồn:

~~~text
source = concat(takeWhile(P), dropWhile(P))
~~~

Bất biến này không có nghĩa hai operation tự chia sẻ một lần duyệt. Chúng là **hai pipeline độc lập** (trong ví dụ, mỗi lần tạo Stream mới từ mảng). Khi nguồn thay đổi giữa hai lần duyệt hoặc predicate có trạng thái/tác dụng phụ, so sánh không còn đáng tin.

### Checklist các trường hợp biên

| Trường hợp | Kết quả cần xác nhận |
| --- | --- |
| Nguồn rỗng | Cả ba đều rỗng |
| Phần tử đầu tiên sai | `takeWhile` rỗng, `dropWhile` giữ cả nguồn |
| Tất cả đều đúng | `takeWhile` giữ cả nguồn, `dropWhile` rỗng |
| Tất cả đều sai | `filter`, `takeWhile` rỗng; `dropWhile` giữ cả nguồn |
| Dữ liệu đúng rồi sai rồi đúng | `takeWhile` **không** lấy những phần tử đúng ở cuối |
| Có nhiều phần tử bằng mốc | Kiểm tra rõ toán tử `<` hay `<=` |
| Nguồn có phần tử null | Chọn chính sách bỏ null hoặc xem null là ranh giới |
| Nguồn unordered | Không assert đúng một tiền tố/hậu tố theo thứ tự gốc |
| Parallel ordered | Ngữ nghĩa kết quả vẫn theo encounter order |
| Nguồn vô hạn | Chứng minh pipeline có thể kết thúc hoặc thêm giới hạn hợp lý |

## 17. Hiệu năng, lazy evaluation và rủi ro với callback có trạng thái

### 17.1. filter là stateless; takeWhile/dropWhile là stateful

`filter` là **stateless intermediate operation**: kết quả chấp nhận hay loại một phần tử không đòi nhớ đã thấy phần tử nào trước đó.

`takeWhile` và `dropWhile` là **stateful intermediate operations** đối với ordered stream: chúng cần xác định vị trí xảy ra **lần đầu tiên predicate không thỏa** để quyết định tiền tố/hậu tố.

`takeWhile` còn là operation **short-circuiting**: khi gặp ranh giới phù hợp trên ordered stream, nó có thể kết thúc lấy dữ liệu từ nguồn trước khi tiêu thụ toàn bộ nguồn. `dropWhile` không làm hậu tố biến mất; nếu terminal muốn toàn bộ hậu tố, các phần tử sau ranh giới vẫn phải được xử lý.

### 17.2. Parallel không đảm bảo tăng tốc

Trên nguồn ordered, xác định tiền tố chính xác trong parallel stream có thể tốn phối hợp giữa các nhánh. Điều này đặc biệt đáng chú ý với `takeWhile`, `dropWhile`, `limit` và `skip`. Nếu yêu cầu nghiệp vụ cho phép không cần encounter order, `unordered()` có thể tạo cơ hội tối ưu, **nhưng nó thay đổi hợp đồng của hai phép while**.

Không có một ngưỡng phần tử cố định để kết luận parallel nhanh hơn. Phải đo với kích thước và phân bố dữ liệu đại diện, đặc biệt khi ranh giới xuất hiện rất sớm hoặc rất muộn.

### 17.3. Không đưa state bên ngoài vào predicate

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

// Không nên xây ngữ nghĩa ranh giới dựa vào counter mutable bên ngoài:
AtomicInteger calls = new AtomicInteger();

int[] result = IntStream.range(0, 20)
    .parallel()
    .takeWhile(n -> calls.incrementAndGet() < 5)
    .toArray();
~~~

`AtomicInteger` làm phép tăng nguyên tử, **không** làm cho số lần/ thứ tự gọi predicate trở thành một quy tắc ổn định theo encounter order. Với parallel, kết quả có thể phụ thuộc lịch chia việc và thực thi; ý định “chỉ lấy bốn phần tử đầu” phải viết bằng `limit(4)` trên nguồn ordered, không bằng biến đếm trong predicate.

### 17.4. Đừng so sánh qua side effect của peek

~~~java
// Không dùng số lần in ra từ peek để khẳng định
// Stream bắt buộc duyệt hết hay bỏ qua chính xác bao nhiêu phần tử.
~~~

Một số terminal operation có thể tối ưu hoặc dừng sớm; callback của các intermediate operation không phải giao thức audit đáng tin cậy. Hãy kiểm tra đầu ra và hợp đồng nguồn. Nếu cần đo hiệu năng, dùng công cụ benchmark phù hợp và số liệu đại diện.

## 18. Những nhầm lẫn cần tránh

### Nhầm lẫn 1: takeWhile là filter có tốc độ cao hơn

Không. `takeWhile` chỉ lấy tiền tố thỏa predicate, nên khác `filter` nếu có phần tử thỏa phía sau một phần tử không thỏa. Sự khác biệt **ngữ nghĩa** phải được quyết định trước câu chuyện hiệu năng.

### Nhầm lẫn 2: dropWhile luôn loại mọi phần tử thỏa predicate

Không. Nó chỉ bỏ **tiền tố liên tiếp**. Khi bắt đầu giữ hậu tố, những phần tử còn lại đều được giữ dù có thể thỏa predicate.

### Nhầm lẫn 3: takeWhile tự sắp dữ liệu

Không. Nó phụ thuộc encounter order của nguồn. Nếu bài toán cần “mọi phần tử nhỏ hơn mốc” mà dữ liệu không bảo đảm thứ tự, `filter` mới là lựa chọn đúng.

### Nhầm lẫn 4: đặt filter trước takeWhile luôn tương đương làm ngược lại

Không. Bước `filter` có thể xóa một phần tử phá vỡ tiền tố, làm `takeWhile` đi xa hơn. Bài tập 8 đã chỉ ra kết quả khác nhau.

### Nhầm lẫn 5: parallel đồng nghĩa unordered

Không. `parallel()` chọn chế độ thực thi; `unordered()` bỏ ràng buộc encounter order. Parallel ordered stream vẫn duy trì ngữ nghĩa tiền tố/hậu tố theo thứ tự nguồn.

### Nhầm lẫn 6: takeWhile trên nguồn vô hạn luôn kết thúc

Không. Nó chỉ có thể kết thúc nếu cuối cùng gặp phần tử không thỏa predicate (hoặc terminal phía sau dừng sớm). Nếu predicate luôn đúng và không có giới hạn khác, pipeline có thể không bao giờ hoàn tất.

### Nhầm lẫn 7: dropWhile(P).findFirst() luôn có giá trị

Không. Nếu nguồn rỗng hoặc **toàn bộ phần tử đều thỏa `P`**, hậu tố rỗng và `findFirst()` trả `Optional.empty()`.

### Nhầm lẫn 8: có thể dùng lại một Stream cho cả ba phép

Không. Mỗi terminal operation tiêu thụ Stream. Muốn so sánh, tạo ba Stream mới từ cùng nguồn ổn định hoặc một `Supplier<Stream<T>>` tạo Stream mới mỗi lần.

### Nhầm lẫn 9: phương thức takeWhile có trên Java 8

Không. `takeWhile` và `dropWhile` được bổ sung ở **Java 9**. Nếu dự án bắt buộc chạy Java 8, cần cách tiếp cận khác hoặc thư viện phù hợp, không thể biên dịch trực tiếp những lời gọi này bằng Java 8.

## 19. Bảng ra quyết định và bài tự kiểm tra

| Yêu cầu thực tế | Operation phù hợp | Lý do |
| --- | --- | --- |
| Lấy mọi giao dịch có số tiền lớn hơn ngưỡng | `filter` | Xét toàn nguồn, không phụ thuộc ranh giới |
| Lấy các bước thành công **trước lần lỗi đầu tiên** | `takeWhile` | Chính xác là tiền tố liên tiếp |
| Xem nhật ký **từ lỗi đầu tiên** trở đi | `dropWhile` | Giữ hậu tố kể cả các bước thành công sau lỗi |
| Lấy mọi phép đo nhiệt độ dưới ngưỡng | `filter` | Có thể có số đo dưới ngưỡng sau lần vượt ngưỡng |
| Lấy các giá trị ban đầu của dãy tăng trước cutoff | `takeWhile` | Predicate theo cutoff đơn điệu theo thứ tự nguồn |
| Bỏ toàn bộ giá trị ban đầu trước cutoff trong dãy tăng | `dropWhile` | Bắt đầu tại phần tử không thỏa đầu tiên |
| Lấy đúng `k` phần tử đầu, không liên quan predicate | `limit(k)` | Ràng buộc số lượng thay vì điều kiện |
| Lấy phần tử phá vỡ tiền tố | `dropWhile(P).findFirst()` | Trả Optional, có thể vắng mặt |
| Lấy bất kỳ phần tử phù hợp trong nguồn không thứ tự | `filter(P).findAny()` | Không yêu cầu tiền tố |
| Yêu cầu phân trang ổn định | Thứ tự xác định + `skip/limit` hoặc cơ chế phân trang chuyên dụng | `unordered().takeWhile` không có ranh giới cố định |

### Câu hỏi tự kiểm tra

1. **Với `[1,4,7,2]` và `P(n) = n < 5`, `filter(P)` trả gì?** `[1,4,2]`.
2. **Cùng nguồn đó, `takeWhile(P)` trả gì?** `[1,4]`.
3. **Cùng nguồn đó, `dropWhile(P)` trả gì?** `[7,2]`.
4. **Có đúng `dropWhile(P) = filter(P.negate())` không?** Không nói chung; chỉ có thể trùng trên nguồn có cấu trúc thỏa predicate rồi không thỏa liên tục.
5. **Khi nào `takeWhile(P)` bằng `filter(P)`?** Khi không có phần tử thỏa predicate nào xuất hiện sau phần tử đầu tiên không thỏa trong encounter order.
6. **Nếu phần tử đầu tiên không thỏa `P`, `takeWhile` trả gì?** Stream rỗng.
7. **Nếu tất cả phần tử thỏa `P`, `dropWhile` trả gì?** Stream rỗng.
8. **`dropWhile(P).findFirst()` có thể trả `Optional.empty()` không?** Có.
9. **`parallel()` có làm `takeWhile` trên List tự trở thành unordered không?** Không.
10. **`unordered().takeWhile(P)` có buộc giữ toàn bộ phần tử thỏa `P` không?** Không; có thể giữ bất kỳ tập con nào.
11. **`unordered().dropWhile(P)` có được bỏ phần tử không thỏa `P` không?** Không; nó chỉ được bỏ một tập con của những phần tử thỏa predicate.
12. **Vì sao `filter(Objects::nonNull)` đôi khi cần đứng trước `takeWhile(n -> n < 5)`?** Để tránh NPE do autounboxing null, nhưng điều này cũng làm thay đổi ranh giới nếu null vốn được coi là dấu ngắt.
13. **Với nguồn vô hạn tăng dần, `takeWhile(n < 5)` có kết thúc không?** Có, nếu nguồn phát đến 5.
14. **`filter(n < 5).toArray()` trên nguồn vô hạn tăng dần có kết thúc không?** Không; filter vẫn đọc tiếp để kiểm tra có số thỏa phía sau hay không.
15. **Có nên dùng bộ đếm mutable trong predicate để mô tả ranh giới số lượng không?** Không; dùng `limit` hoặc mô hình dữ liệu rõ ràng.
16. **Nếu muốn giữ tất cả dữ liệu kể từ một sự cố trở đi, dùng gì?** `dropWhile` với predicate mô tả trạng thái “chưa xảy ra sự cố”.
17. **Nếu muốn giữ mọi phần tử không lỗi, kể cả sau lần lỗi đầu, dùng gì?** `filter`.
18. **Dữ liệu phải đáp ứng điều gì để `takeWhile` có ý nghĩa “trước mốc thời gian”?** Có encounter order tương ứng với thời gian, hoặc được sắp đúng theo thời gian trước đó.
19. **Có thể gọi ba terminal operation trên một Stream đã tạo sẵn không?** Không; phải tạo Stream mới mỗi lần.
20. **Java tối thiểu cho `Stream.takeWhile`/`dropWhile` là phiên bản nào?** Java 9.

### Bài mở rộng

**Bài A:** Cho dãy số `[4,6,8,3,10,12]`. Dự đoán ba kết quả với `P(n) = n % 2 == 0`. Giải thích vì sao `dropWhile` giữ cả `10` và `12` dù chúng là số chẵn.

**Bài B:** Một danh sách phiên kết nối có cờ `connected`. Tính tổng thời lượng của **đoạn kết nối liên tiếp ban đầu** và so sánh với tổng thời lượng của **tất cả phiên connected**; dùng `takeWhile` và `filter` tương ứng.

**Bài C:** Sửa ví dụ nhật ký để trả về `Optional<Event> firstError` bằng `dropWhile(e -> !"ERROR".equals(e.level())).findFirst()`. Kiểm tra nhật ký không có lỗi và nhật ký bắt đầu bằng lỗi.

**Bài D:** Viết kiểm thử cho `IntStream.rangeClosed(1,1000).parallel().takeWhile(n -> n < 100)`, xác minh kết quả ordered. Sau đó thêm `unordered()` và chỉ kiểm tra các bất biến đúng theo đặc tả, không khẳng định đúng 99 phần tử.

**Ghi nhớ:** `filter(P)` chọn **mọi phần tử thỏa `P`**. Trên nguồn có thứ tự, `takeWhile(P)` chỉ giữ **tiền tố liên tiếp** thỏa `P`, còn `dropWhile(P)` bỏ tiền tố đó và giữ **toàn bộ hậu tố**, kể cả những phần tử thỏa `P` xuất hiện sau ranh giới. Ba operation có thể trùng kết quả trong các trường hợp đặc biệt nhưng không thể thay thế tùy ý. Hãy xác định yêu cầu nghiệp vụ, encounter order, chính sách dữ liệu thiếu và điều kiện kết thúc trước khi chọn operation hoặc bật xử lý song song.
