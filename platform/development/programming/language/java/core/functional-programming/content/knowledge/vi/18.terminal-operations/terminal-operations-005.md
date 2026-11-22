# Kết quả của các phép kiểm tra khi Stream rỗng trong Java

Khi một `Stream` **không có phần tử nào**, ba thao tác kiểm tra bằng predicate của Java Stream có kết quả mặc định rất dễ gây nhầm:

| Terminal operation | Câu hỏi nó trả lời | Kết quả với stream rỗng |
| --- | --- | --- |
| `anyMatch(predicate)` | **Có ít nhất một** phần tử thỏa điều kiện không? | **`false`** |
| `allMatch(predicate)` | **Mọi** phần tử có thỏa điều kiện không? | **`true`** |
| `noneMatch(predicate)` | **Không có** phần tử nào thỏa điều kiện phải không? | **`true`** |

Kết quả này **không phụ thuộc predicate kiểm tra điều kiện gì**, miễn predicate là đối tượng hợp lệ. Với nguồn rỗng, không có phần tử nào để gọi `Predicate.test`: không có bằng chứng tồn tại phần tử phù hợp (`anyMatch` là `false`), cũng không có phản ví dụ làm sai phát biểu “tất cả phù hợp” (`allMatch` là `true`), và không có phần tử phù hợp nào (`noneMatch` là `true`).

Điều quan trọng nhất: **`allMatch` trả `true` không chứng minh stream có dữ liệu**. Nếu nghiệp vụ yêu cầu “phải có ít nhất một bản ghi, và mọi bản ghi đều hợp lệ”, cần thêm kiểm tra **không rỗng**.

## 1. Chữ ký, ý nghĩa và điểm chung

Các phương thức trên `Stream<T>` có dạng:

~~~java
// Chữ ký API để tham khảo; không phải tệp Java độc lập.
boolean anyMatch(Predicate<? super T> predicate);
boolean allMatch(Predicate<? super T> predicate);
boolean noneMatch(Predicate<? super T> predicate);
~~~

Các phiên bản tương ứng cũng có trên `IntStream`, `LongStream` và `DoubleStream`, với predicate primitive như `IntPredicate`. Chúng là **terminal operation**: trả về một giá trị `boolean`, tiêu thụ stream, và không cho gọi lại terminal operation trên cùng stream.

Ba phương thức này đều là thao tác **short-circuit** (*có thể dừng sớm*). Chúng không phải `filter`: `filter(predicate)` trả một stream trung gian để xử lý tiếp, còn `anyMatch`, `allMatch`, `noneMatch` kết thúc pipeline và trả kết quả kiểm tra.

Khi không có phần tử, logic dừng sớm áp dụng ngay: mọi kiểm tra đều có thể trả giá trị xác định mà **không gọi predicate lần nào**.

## 2. Ví dụ chạy độc lập: ba kết quả trên nguồn rỗng

Tạo file `EmptyMatchDemo.java`:

~~~java
import java.util.stream.Stream;

public class EmptyMatchDemo {
    public static void main(String[] args) {
        boolean any = Stream.<Integer>empty()
                .anyMatch(n -> n > 0);

        boolean all = Stream.<Integer>empty()
                .allMatch(n -> n > 0);

        boolean none = Stream.<Integer>empty()
                .noneMatch(n -> n > 0);

        System.out.println("anyMatch=" + any);
        System.out.println("allMatch=" + all);
        System.out.println("noneMatch=" + none);
    }
}
~~~

~~~bash
javac --release 17 EmptyMatchDemo.java
java EmptyMatchDemo
~~~

Kết quả:

~~~text
anyMatch=false
allMatch=true
noneMatch=true
~~~

Mỗi phép kiểm tra dùng một **stream mới**. `Stream.<Integer>empty()` viết rõ kiểu phần tử để lambda `n -> n > 0` được kiểm tra với `Integer`; dù không có phần tử thực, kiểu tĩnh vẫn tồn tại.

Đừng viết một biến `Stream<Integer> s = Stream.empty()` rồi lần lượt gọi `s.anyMatch(...)`, `s.allMatch(...)` và `s.noneMatch(...)`: sau terminal operation đầu, stream đã bị sử dụng, không hợp lệ để tiếp tục thao tác. Hãy tạo lại stream từ collection/nguồn, hoặc thiết kế logic xử lý chỉ tiêu thụ một lần.

## 3. Vì sao `allMatch(empty)` là `true`? Sự đúng một cách rỗng

Ở mức logic toán học:

- `anyMatch(p)` tương ứng mệnh đề **tồn tại**: `∃x ∈ S: p(x)`.
- `allMatch(p)` tương ứng mệnh đề **mọi phần tử**: `∀x ∈ S: p(x)`.
- `noneMatch(p)` tương ứng **không tồn tại** phần tử thỏa: `¬∃x ∈ S: p(x)`.

Với tập rỗng `S = ∅`:

- Mệnh đề tồn tại là **sai**, vì không chọn được nhân chứng nào: `anyMatch(p) == false`.
- Mệnh đề mọi phần tử là **đúng một cách rỗng** (*vacuously true*): không có phần tử phản ví dụ `p(x) == false`, nên `allMatch(p) == true`.
- Không tồn tại phần tử thỏa cũng là **đúng**: `noneMatch(p) == true`.

Có thể liên hệ với phần tử đơn vị (*identity*) của hai phép toán:

~~~text
anyMatch:   false OR false OR ...       → false nếu không có toán hạng
allMatch:   true  AND true AND ...      → true  nếu không có toán hạng
noneMatch:  NOT (false OR false OR ...) → true  nếu không có toán hạng
~~~

Đây là **minh họa logic**, không có nghĩa JDK bắt buộc triển khai bằng `reduce` với các phép toán như trên. Nó giúp giải thích nhất quán tại sao kết quả mặc định không phải `false` cho cả ba trường hợp.

Phát biểu “mọi học viên trong lớp đều đạt điểm tối đa” vẫn đúng theo logic nếu lớp không có học viên nào, nhưng trong nghiệp vụ quản lý lớp học có thể **không được chấp nhận**. Sự khác biệt giữa đúng theo logic và hợp lệ theo nghiệp vụ dẫn tới cách kiểm tra ở mục 6.

## 4. Stream có thể rỗng dù nguồn ban đầu không rỗng

`Stream.empty()` là trường hợp rõ ràng nhất, nhưng nguồn rỗng có thể xuất hiện sau một pipeline:

- `List.<T>of().stream()`: collection rỗng ngay từ đầu.
- `Stream.of(...).filter(...)`: mọi phần tử bị loại.
- `Stream.of(...).limit(0)`: giới hạn số phần tử xuống 0.
- `Stream.ofNullable(null)`: tạo stream có **0 phần tử** khi đối số null (Java 9+).
- `flatMap(...)`: mọi nhánh trả stream rỗng, nên kết quả tổng thể rỗng.

Ví dụ độc lập, file `EmptyAfterFilterDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class EmptyAfterFilterDemo {
    public static void main(String[] args) {
        List<Integer> scores = List.of(3, 5, 7);

        boolean anyHigh = scores.stream()
                .filter(n -> n >= 10)
                .anyMatch(n -> n % 2 == 0);

        boolean allEven = scores.stream()
                .filter(n -> n >= 10)
                .allMatch(n -> n % 2 == 0);

        boolean noneEven = scores.stream()
                .filter(n -> n >= 10)
                .noneMatch(n -> n % 2 == 0);

        System.out.println("anyHighEven=" + anyHigh);
        System.out.println("allHighEven=" + allEven);
        System.out.println("noneHighEven=" + noneEven);

        System.out.println("nullable source count="
                + Stream.ofNullable((String) null).count());
    }
}
~~~

~~~bash
javac --release 17 EmptyAfterFilterDemo.java
java EmptyAfterFilterDemo
~~~

Kết quả:

~~~text
anyHighEven=false
allHighEven=true
noneHighEven=true
nullable source count=0
~~~

Dù `scores` ban đầu có ba phần tử, bước `filter(n -> n >= 10)` tạo pipeline **không phát ra phần tử**. Predicate `n -> n % 2 == 0` của phép match không được đánh giá trên phần tử nào. `allHighEven == true` ở đây không có nghĩa “tất cả điểm cao đều chẵn và có ít nhất một điểm cao”; chỉ là **không tìm thấy điểm cao phản ví dụ**.

## 5. Predicate có được gọi khi nguồn rỗng không?

Với predicate hợp lệ, không có phần tử nào để đưa vào `Predicate.test`. Có thể minh họa bằng một bộ đếm **chỉ để học/kiểm thử**. Tạo file `EmptyPredicateCallsDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.stream.Stream;

public class EmptyPredicateCallsDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        Predicate<Integer> counting = n -> {
            calls.incrementAndGet();
            return n > 0;
        };

        boolean any = Stream.<Integer>empty().anyMatch(counting);
        boolean all = Stream.<Integer>empty().allMatch(counting);
        boolean none = Stream.<Integer>empty().noneMatch(counting);

        System.out.println("any=" + any);
        System.out.println("all=" + all);
        System.out.println("none=" + none);
        System.out.println("predicate calls=" + calls.get());
    }
}
~~~

~~~bash
javac --release 17 EmptyPredicateCallsDemo.java
java EmptyPredicateCallsDemo
~~~

Kết quả:

~~~text
any=false
all=true
none=true
predicate calls=0
~~~

Không nhầm hai điều:

1. **Predicate không được gọi** nếu stream thật sự rỗng: không có đối số để kiểm tra.
2. **Tham số predicate vẫn phải hợp lệ**: truyền tham chiếu `null` làm predicate cho `anyMatch(null)`, `allMatch(null)` hoặc `noneMatch(null)` không hợp lệ và có thể ném `NullPointerException` ngay cả khi stream rỗng. Java vẫn có quyền kiểm tra tính hợp lệ của đối số API.

Không nên dùng side effect trong predicate để điều khiển nghiệp vụ: khi stream không rỗng, các toán tử short-circuit có thể dừng sớm, và trên parallel stream có thể kiểm tra các phần tử theo thứ tự/luồng thực thi khác. Bộ đếm ở đây chỉ để quan sát trường hợp rỗng.

## 6. Bẫy nghiệp vụ: “tất cả hợp lệ” có yêu cầu có dữ liệu không?

Một yêu cầu thường gặp là “đơn hàng chỉ được phê duyệt nếu **có ít nhất một mặt hàng** và **tất cả mặt hàng có số lượng dương**”. Cách viết:

~~~java
boolean valid = items.stream().allMatch(item -> item.quantity() > 0);
~~~

**Không đủ** nếu `items` có thể rỗng: kết quả sẽ là `true` mặc dù không có mặt hàng nào.

Nếu nguồn là `Collection` còn dùng được nhiều lần, kết hợp `!isEmpty()` với `allMatch`:

~~~java
boolean valid = !items.isEmpty()
        && items.stream().allMatch(item -> item.quantity() > 0);
~~~

Phần `&&` làm việc theo short-circuit: khi collection rỗng, không cần tạo và tiêu thụ stream cho điều kiện thứ hai.

Tạo file `NonEmptyValidationDemo.java`:

~~~java
import java.util.List;

public class NonEmptyValidationDemo {
    record LineItem(String sku, int quantity) {}

    static boolean everyQuantityPositive(List<LineItem> items) {
        return items.stream().allMatch(item -> item.quantity() > 0);
    }

    static boolean validOrder(List<LineItem> items) {
        return !items.isEmpty()
                && items.stream().allMatch(item -> item.quantity() > 0);
    }

    public static void main(String[] args) {
        List<LineItem> empty = List.of();
        List<LineItem> good = List.of(
                new LineItem("A", 2),
                new LineItem("B", 1));
        List<LineItem> bad = List.of(
                new LineItem("A", 2),
                new LineItem("B", 0));

        System.out.println("empty all positive="
                + everyQuantityPositive(empty));
        System.out.println("empty valid order=" + validOrder(empty));
        System.out.println("good valid order=" + validOrder(good));
        System.out.println("bad valid order=" + validOrder(bad));
    }
}
~~~

~~~bash
javac --release 17 NonEmptyValidationDemo.java
java NonEmptyValidationDemo
~~~

Kết quả:

~~~text
empty all positive=true
empty valid order=false
good valid order=true
bad valid order=false
~~~

Mô hình trên tách biệt rõ:

- **Tính đúng của mọi phần tử:** `allMatch(...)`.
- **Ràng buộc có ít nhất một phần tử:** `!items.isEmpty()`.

Không “sửa” `allMatch` thành `anyMatch`: `anyMatch` chỉ cần **một** phần tử đạt, còn các phần tử khác có thể vi phạm.

Với nguồn chỉ có một `Stream` dùng một lần (không phải collection), không thể gọi `count()` rồi tiếp tục gọi `allMatch()` trên cùng instance. Có thể kiểm tra nguồn ở lớp collection/repository, thu dữ liệu thành một cấu trúc thích hợp nếu kích thước cho phép, hoặc xây dựng một phép tổng hợp duy nhất lưu cả `count` và cờ hợp lệ nếu nhu cầu yêu cầu xử lý một lượt. Khi dữ liệu lớn hoặc vô hạn, phải xem lại chiến lược vật chất hóa và terminal operation.

## 7. Bảng chân trị: rỗng, tất cả đúng, trộn đúng/sai, tất cả sai

Đối với **cùng một predicate** trên các tập giá trị tương ứng:

| Trạng thái phần tử | `anyMatch(p)` | `allMatch(p)` | `noneMatch(p)` |
| --- | --- | --- | --- |
| **0 phần tử** | `false` | `true` | `true` |
| Ít nhất một phần tử, **tất cả đúng** | `true` | `true` | `false` |
| Có phần tử đúng **và** sai | `true` | `false` | `false` |
| Ít nhất một phần tử, **tất cả sai** | `false` | `false` | `true` |

Đọc bảng theo câu hỏi nghiệp vụ:

- `anyMatch`: “Có nhân chứng thỏa điều kiện không?”
- `allMatch`: “Có phản ví dụ nào không?” Nếu không có phản ví dụ, kết quả đúng — kể cả vì không có phần tử.
- `noneMatch`: “Có phần tử nào vi phạm yêu cầu không được thỏa điều kiện không?” Nếu không có phần tử nào, câu trả lời là không.

Ví dụ với predicate `n -> n % 2 == 0`, một `List<Integer>` rỗng cho kết quả `false / true / true`; `[2,4]` cho `true / true / false`; `[2,3]` cho `true / false / false`; `[1,3]` cho `false / false / true`.

## 8. Quan hệ logic giữa ba phép kiểm tra

Với một predicate `p` **thuần, ổn định** và cùng chuỗi giá trị có thể tái tạo:

- `noneMatch(p)` tương đương `!anyMatch(p)`.
- `allMatch(p)` tương đương `noneMatch(p.negate())`.
- `allMatch(p)` tương đương `!anyMatch(p.negate())`.
- `anyMatch(p)` tương đương `!allMatch(p.negate())`.

Những đẳng thức này cũng đúng trên **stream rỗng** theo logic:

~~~text
noneMatch(p)       = true
!anyMatch(p)       = !false = true
allMatch(p)        = true
noneMatch(not p)   = true
~~~

Tạo file `MatchEquivalencesDemo.java`:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class MatchEquivalencesDemo {
    static void check(List<Integer> numbers) {
        Predicate<Integer> positive = n -> n > 0;

        boolean nonePositive = numbers.stream().noneMatch(positive);
        boolean notAnyPositive = !numbers.stream().anyMatch(positive);
        boolean allNonPositive =
                numbers.stream().allMatch(positive.negate());

        System.out.println(
                "size=" + numbers.size()
                + " none=" + nonePositive
                + " notAny=" + notAnyPositive
                + " allNegated=" + allNonPositive);
    }

    public static void main(String[] args) {
        check(List.of());
        check(List.of(-2, 0));
        check(List.of(-2, 3));
    }
}
~~~

~~~bash
javac --release 17 MatchEquivalencesDemo.java
java MatchEquivalencesDemo
~~~

Kết quả:

~~~text
size=0 none=true notAny=true allNegated=true
size=2 none=true notAny=true allNegated=true
size=2 none=false notAny=false allNegated=false
~~~

Các biến thể đều tạo **stream mới** từ cùng collection. Với nguồn phát dữ liệu thay đổi giữa các lần tạo stream, predicate có side effect, hoặc phụ thuộc thời gian, không suy ra các kết quả của **những lần chạy khác nhau** luôn bằng nhau; đẳng thức là tính chất logic trên **cùng dữ liệu và cùng predicate**.

Đừng lạm dụng đẳng thức để làm code khó đọc: nếu cần diễn đạt “không có lỗi nào”, `noneMatch(isError)` thường rõ nghĩa hơn `!anyMatch(isError)`; nếu cần “mọi phần tử hợp lệ”, `allMatch(isValid)` nói rõ ý định.

## 9. Short-circuit trên nguồn không rỗng

Giá trị mặc định của stream rỗng dễ nhớ hơn khi đặt cạnh **điều kiện dừng sớm** của từng phép:

| Phép kiểm tra | Khi nào có thể chốt `true` sớm? | Khi nào có thể chốt `false` sớm? | Nếu đi hết mà chưa tìm được điều kiện dừng |
| --- | --- | --- | --- |
| `anyMatch(p)` | Thấy **một** phần tử thỏa `p` | Không thể chốt false nếu vẫn có phần tử chưa xét | `false` |
| `allMatch(p)` | Không thể chốt true nếu vẫn có phần tử chưa xét | Thấy **một** phần tử **không thỏa** `p` | `true` |
| `noneMatch(p)` | Không thể chốt true nếu vẫn có phần tử chưa xét | Thấy **một** phần tử thỏa `p` | `true` |

Với stream rỗng, trạng thái “đi hết mà chưa có phần tử nào” đã xảy ra ngay từ đầu, dẫn đến `false / true / true`.

Ví dụ:

~~~java
// Minh họa: các biểu thức nằm trong phương thức Java.
boolean hasEven = java.util.stream.Stream.of(3, 5, 8, 9)
        .anyMatch(n -> n % 2 == 0);    // true

boolean everyOdd = java.util.stream.Stream.of(3, 5, 8, 9)
        .allMatch(n -> n % 2 != 0);     // false

boolean noNegative = java.util.stream.Stream.of(3, 5, 8, 9)
        .noneMatch(n -> n < 0);        // true
~~~

Các phép match không bắt buộc kiểm tra mọi phần tử để trả được kết quả. Với stream song song, không bảo đảm **thứ tự hay số lần** predicate được gọi. Không phụ thuộc vào side effect như tăng biến mutable, cập nhật database hoặc ghi log để làm đầu ra nghiệp vụ.

## 10. Không nhầm phép match với các terminal operation khác trên Stream rỗng

“Kiểm tra điều kiện” thường chỉ ba phép match, nhưng khi đọc pipeline cũng cần phân biệt các kết quả terminal liên quan:

| Terminal operation trên nguồn rỗng | Kiểu trả về | Kết quả thường gặp |
| --- | --- | --- |
| `anyMatch(p)` | `boolean` | `false` |
| `allMatch(p)` | `boolean` | `true` |
| `noneMatch(p)` | `boolean` | `true` |
| `count()` | `long` | `0L` |
| `findFirst()` | `Optional<T>` | `Optional.empty()` |
| `findAny()` | `Optional<T>` | `Optional.empty()` |
| `min(comparator)` / `max(comparator)` | `Optional<T>` | `Optional.empty()` |
| `Stream.toList()` | `List<T>` | Danh sách rỗng |
| `IntStream.sum()` | `int` | `0` |
| `IntStream.average()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `reduce(identity, accumulator)` | `T` | Giá trị identity, nếu toán tử/đối số hợp lệ |

Ví dụ độc lập, `OtherEmptyTerminalsDemo.java`:

~~~java
import java.util.Comparator;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class OtherEmptyTerminalsDemo {
    public static void main(String[] args) {
        System.out.println("count=" + Stream.empty().count());
        System.out.println("findFirst="
                + Stream.<String>empty().findFirst());
        System.out.println("min="
                + Stream.<Integer>empty().min(Comparator.naturalOrder()));
        System.out.println("sum=" + IntStream.empty().sum());
        System.out.println("average=" + IntStream.empty().average());
        System.out.println("reduce="
                + IntStream.empty().reduce(10, Integer::sum));
    }
}
~~~

~~~bash
javac --release 17 OtherEmptyTerminalsDemo.java
java OtherEmptyTerminalsDemo
~~~

Kết quả:

~~~text
count=0
findFirst=Optional.empty
min=Optional.empty
sum=0
average=OptionalDouble.empty
reduce=10
~~~

`Optional.empty()` là **một đối tượng Optional không có giá trị**, không phải một `null`. Khi không có phần tử, `findFirst` và `min` trả kiểu này thay vì `boolean`. Đừng thay thế nhầm `allMatch` bằng `findFirst().isPresent()`: `isPresent()` kiểm tra **sự tồn tại** phần tử, không chứng minh tất cả phần tử thỏa điều kiện.

## 11. Khóa học thực hành: nhận biết bẫy null và điều kiện rỗng

Nếu một stream có thể chứa phần tử null, viết:

~~~java
// Minh họa trên Stream<String> có thể chứa null.
boolean allLong = source.allMatch(s -> s.length() >= 3);
~~~

có thể ném `NullPointerException` khi predicate được gọi với phần tử null. **Stream rỗng** không ném lỗi vì không gọi predicate, nhưng điều đó không chứng minh lambda an toàn trên stream có dữ liệu. Có thể quyết định rõ chính sách:

~~~java
// Null được coi là không hợp lệ:
boolean allValid = source.allMatch(
        s -> s != null && s.length() >= 3);
~~~

Nếu bạn chọn `filter(Objects::nonNull)` trước `allMatch`, mọi phần tử null sẽ bị **loại bỏ**; khi tất cả phần tử đều null, kết quả sau lọc rỗng và `allMatch` lại thành true. Vì vậy “loại dữ liệu null” và “xem dữ liệu null là không hợp lệ” là **hai đặc tả khác nhau**.

Nguyên tắc tương tự áp dụng với bộ lọc quy tắc nghiệp vụ: nếu `filter` loại hết bản ghi không hợp lệ rồi `allMatch` trên những bản ghi còn lại, `allMatch` có thể đúng vì stream đã rỗng. Hãy hỏi bạn muốn **kiểm tra mọi đầu vào**, hay **chỉ kiểm tra tập còn lại sau lọc**.

## 12. Primitive stream, parallel và các lưu ý về tính đúng

Với `IntStream.empty()`, `LongStream.empty()`, `DoubleStream.empty()`, ba phép match trả đúng bộ giá trị logic `false / true / true`, không khác `Stream<T>`.

~~~java
// Minh họa trong phương thức:
boolean any = java.util.stream.IntStream.empty()
        .anyMatch(n -> n > 10);       // false
boolean all = java.util.stream.IntStream.empty()
        .allMatch(n -> n > 10);       // true
boolean none = java.util.stream.IntStream.empty()
        .noneMatch(n -> n > 10);      // true
~~~

Trên **parallel stream**, ý nghĩa boolean của các match không thay đổi; chỉ cách triển khai/đánh giá có thể khác. Một `parallelStream()` rỗng vẫn trả `false / true / true`. Không giả định một predicate sẽ được gọi lần lượt theo encounter order, hoặc rằng predicate side effect được thực thi đúng một lần cho mỗi phần tử trước khi short-circuit.

Ngoài ra, ba phép match **không đảm bảo kết thúc** trên một nguồn vô hạn khi không xuất hiện điều kiện chốt kết quả. Ví dụ, `Stream.iterate(1, n -> n + 1).allMatch(n -> n > 0)` không nên dùng làm phép thử sẽ hoàn tất: nếu nguồn không kết thúc và không xuất hiện phản ví dụ, `allMatch` không có cơ sở chốt true. `anyMatch` có thể dừng nếu tìm được một phần tử phù hợp; `noneMatch` có thể dừng false khi tìm được phần tử phù hợp. Nguồn rỗng là trường hợp đặc biệt **kết thúc ngay**, không có bài toán tiến trình này.

Các giá trị rỗng áp dụng khi stream **thật sự có zero phần tử** và predicate hợp lệ, bất kể đã tạo từ `empty()`, `filter`, `limit(0)` hay dữ liệu gốc không có phần tử.

## 13. Lỗi thường gặp và cách tránh

1. **“`allMatch == true` nên chắc chắn có dữ liệu hợp lệ.”** Sai khi nguồn rỗng: kết quả true theo vacuous truth. Thêm `!isEmpty()` nếu cần ít nhất một bản ghi.
2. **“`noneMatch == true` nghĩa là tất cả đã được kiểm tra.”** Trên nguồn rỗng không có phần tử nào được kiểm tra; không có nhân chứng thỏa predicate là đủ.
3. **“`anyMatch`, `allMatch`, `noneMatch` luôn trả false khi rỗng.”** Không đúng: chỉ `anyMatch` false; hai phép còn lại true.
4. **“`allMatch` và `noneMatch` mâu thuẫn khi cùng true.”** Không: với nguồn rỗng, cả “mọi phần tử đều thỏa” và “không phần tử nào thỏa” đều đúng theo logic.
5. **“Predicate luôn được gọi ít nhất một lần.”** Không: nguồn rỗng không có đối số; trên nguồn không rỗng cũng có short-circuit.
6. **“Dùng lại một stream cho cả ba phép.”** Không hợp lệ: stream được tiêu thụ bởi terminal operation; cần tạo stream mới từ nguồn có thể truy cập lại.
7. **“`filter` trước `allMatch` vẫn kiểm tra toàn bộ nguồn ban đầu.”** Không: `allMatch` chỉ nhận phần tử còn lại sau filter, có thể là tập rỗng.
8. **“`allMatch(null)` hợp lệ nếu stream rỗng.”** Không: predicate null vi phạm hợp đồng API, có thể ném `NullPointerException`.
9. **“`findFirst` trên stream rỗng trả boolean false.”** Không: trả `Optional.empty()`. `count` trả `0L`, và `toList` trả một danh sách rỗng.
10. **“Predicate side effect sẽ luôn chạy để cập nhật trạng thái.”** Không: short-circuit, tối ưu hóa và parallel có thể làm thay đổi số lần/thứ tự gọi, khiến logic không đáng tin cậy.
11. **“Stream vô hạn có `allMatch` chắc chắn trả true nếu mọi phần tử đều đạt.”** Không: nếu không có điểm kết thúc, không thể chốt true bằng việc kiểm tra hữu hạn phần tử.
12. **“Kiểm tra `!anyMatch(p)` và `noneMatch(p)` trên hai lần lấy dữ liệu bất kỳ luôn giống nhau.”** Chỉ suy ra khi dữ liệu và predicate ổn định tương đương ở hai lần tiêu thụ.

## 14. Checklist đọc và viết pipeline kiểm tra

Khi thấy `.anyMatch(...)`, `.allMatch(...)` hoặc `.noneMatch(...)`, hãy tự hỏi:

- Stream đang có thể **rỗng** từ đầu, hay trở thành rỗng sau `filter`, `flatMap`, `limit(0)`?
- Nghiệp vụ muốn **tồn tại ít nhất một**, **mọi phần tử**, hay **không tồn tại phần tử thỏa**?
- Nếu nguồn rỗng, **`false / true / true`** có đúng với yêu cầu không?
- `allMatch == true` có cần kèm **ràng buộc ít nhất một phần tử** không?
- Predicate có thể gặp `null`, phụ thuộc trạng thái thay đổi, hoặc gây side effect không?
- Terminal operation đã tiêu thụ stream chưa? Có đang cố sử dụng lại cùng stream không?
- Với nguồn vô hạn/parallel, điều kiện dừng sớm và độ ổn định của predicate có phù hợp không?

**Ghi nhớ:** đối với stream rỗng, **`anyMatch(p) == false`**, **`allMatch(p) == true`**, **`noneMatch(p) == true`**. `allMatch` và `noneMatch` đúng vì **không có phản ví dụ/nhân chứng**, không phải vì đã kiểm tra một phần tử hợp lệ nào. Nếu nghiệp vụ yêu cầu ít nhất một phần tử, hãy kiểm tra điều đó **riêng**.
