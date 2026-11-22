# Predicate.not và phủ định method reference (Java 11+)

**Chủ đề: Tiện ích dữ liệu.** Khi lọc dữ liệu bằng Stream hoặc xây dựng điều kiện kiểm tra, ta thường có một phương thức trả về `boolean`, chẳng hạn `String.isBlank()`, nhưng lại cần lấy phần tử **không thỏa** điều kiện. Java 11 bổ sung phương thức tĩnh `Predicate.not(...)` để diễn đạt phép phủ định gọn và rõ ngay quanh một method reference. Tính năng này tiếp tục được hỗ trợ trong Java hiện đại.

Bài học giải thích bản chất, cách viết, suy luận kiểu, an toàn với `null`, khác biệt với `Predicate.negate()`, các phép kết hợp điều kiện và bộ test thực thi được với JDK 11 trở lên.

## 1. Nền tảng: Predicate<T> và method reference

`java.util.function.Predicate<T>` là functional interface có phương thức:

```java
boolean test(T value);
```

Giá trị trả về của `test` là `true` nếu đối số thỏa điều kiện, và `false` trong trường hợp ngược lại. Ví dụ:

```java
java.util.function.Predicate<String> isBlank = String::isBlank;
```

Đây là **đoạn minh họa**, có thể đặt bên trong một phương thức Java. `String::isBlank` là method reference trỏ đến **instance method không có tham số**: đối số kiểu `String` truyền cho `Predicate.test` được sử dụng như đối tượng nhận lời gọi (receiver).

```text
isBlank.test("   ")  -> true
isBlank.test("Java") -> false
```

Một `Stream.filter(predicate)` sẽ **giữ lại** phần tử khi `predicate.test(element) == true`. Vì thế:

- `filter(String::isBlank)` giữ chuỗi rỗng hoặc chỉ chứa whitespace Java.
- `filter(Predicate.not(String::isBlank))` giữ chuỗi có ít nhất một code point không phải whitespace Java.

Lưu ý rằng `filter` chỉ chọn phần tử; không làm sạch, đổi nội dung hay xóa phần tử khỏi collection gốc.

## 2. API Predicate.not: chữ ký và hợp đồng

Từ Java 11, `Predicate<T>` có phương thức tĩnh:

```java
static <T> Predicate<T> not(Predicate<? super T> target)
```

Đây là **chữ ký API**, không phải một method cần tự định nghĩa lại. Hợp đồng của nó:

1. Nhận một predicate gốc có thể kiểm tra đối số kiểu `T` (hoặc kiểu cha của `T`).
2. Trả về một predicate khác với **kết quả logic bị phủ định**: đúng chuyển thành sai, sai chuyển thành đúng.
3. Theo Javadoc, kết quả được tạo bằng việc gọi `target.negate()`.
4. Nếu đối số `target` chính nó là `null`, lời gọi `Predicate.not(null)` ném `NullPointerException`.

| `target.test(x)` | `Predicate.not(target).test(x)` |
| :---: | :---: |
| `true` | `false` |
| `false` | `true` |

`Predicate.not` không tự kiểm tra `null` của **dữ liệu** được đưa vào sau này, không bắt exception của predicate và không biến kết quả trả về thành giá trị mặc định nào khác.

## 3. Vì sao method reference cần Predicate.not?

Một biểu thức method reference không phải là giá trị boolean có thể viết toán tử `!` ngay phía trước. Các cách viết sau sai cú pháp (chỉ minh họa lỗi, **không biên dịch**):

```java
// stream.filter(!String::isBlank);
// stream.filter(String::isBlank.negate());
```

Ba cách phủ định hợp lệ sau tương đương với cùng đối số không null:

```java
// Viết trực tiếp bằng lambda
Predicate<String> a = s -> !s.isBlank();

// Java 11+: phương thức tĩnh giúp dùng method reference tại chỗ
Predicate<String> b = Predicate.not(String::isBlank);

// Dùng negate trên một Predicate đã có tên
Predicate<String> isBlank = String::isBlank;
Predicate<String> c = isBlank.negate();
```

Đoạn trên giả định đã import `java.util.function.Predicate`; hãy đặt bên trong một phương thức khi thử.

**Khi nào dùng cách nào?** Với pipeline muốn ngắn gọn như `stream.filter(Predicate.not(String::isBlank))`, dùng `Predicate.not` giúp rõ ý. Khi đã có predicate tên `isBlank`, gọi `isBlank.negate()` tự nhiên và tương đương. Lambda `s -> !s.isBlank()` vẫn hợp lệ và có ích khi cần thêm xử lý; không có yêu cầu phải thay mọi lambda bằng method reference.

### Ví dụ chạy độc lập: PredicateNotBasics.java

```java
import java.util.List;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PredicateNotBasics {
    public static void main(String[] args) {
        List<String> values = List.of(
                "Java", "", " \t ", "Spring", "Kotlin");

        List<String> nonBlank = values.stream()
                .filter(Predicate.not(String::isBlank))
                .collect(Collectors.toList());

        long nonEmptyCount = values.stream()
                .filter(Predicate.not(String::isEmpty))
                .count();

        Predicate<String> isBlank = String::isBlank;
        Predicate<String> hasContent = isBlank.negate();

        System.out.println(nonBlank);
        System.out.println(nonEmptyCount);
        System.out.println(hasContent.test("Java 11"));
        System.out.println(hasContent.test(" \t "));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateNotBasics.java
java PredicateNotBasics
```

Kết quả:

```text
[Java, Spring, Kotlin]
4
true
false
```

Trong dữ liệu có năm chuỗi: ba chuỗi chứa chữ, một chuỗi rỗng và một chuỗi chỉ chứa SPACE/TAB. `String.isBlank()` trả về `true` cho hai chuỗi cuối, trong khi `String.isEmpty()` chỉ trả về `true` với chuỗi có độ dài 0. Do đó phủ định `isEmpty` giữ **4** phần tử, bao gồm `" \t "`; phủ định `isBlank` chỉ giữ **3** phần tử chứa chữ.

Định nghĩa `isBlank` dùng `Character.isWhitespace`; với một số Unicode non-breaking spaces, ví dụ U+00A0, Java không xem đó là whitespace. Vì vậy `Predicate.not(String::isBlank).test("\u00A0")` là `true`. Nếu nghiệp vụ muốn coi NBSP là “trống”, cần định nghĩa predicate riêng và viết test rõ, không tự thay đổi ý nghĩa API.

## 4. Suy luận kiểu của Predicate.not

`Predicate.not` là một **generic method**. Kiểu `T` được suy ra từ method reference, từ functional interface đích và ngữ cảnh.

```java
Predicate<String> notBlank = Predicate.not(String::isBlank);
Predicate<String> blank = String::isBlank;
Predicate<String> sameResult = blank.negate();
```

Đây là các đoạn minh họa với `Predicate` đã import. Trong pipeline `Stream<String>`, phương thức `filter` nhận `Predicate<? super String>`, tạo ngữ cảnh để compiler kiểm tra method reference.

Nếu một biểu thức generic quá phức tạp khiến compiler không xác định được kiểu mong muốn, hãy khai báo biến `Predicate<String>` như trên, hoặc ghi rõ *type witness*:

```java
var notBlank = Predicate.<String>not(String::isBlank);
```

Kết quả vẫn là `Predicate<String>`. `var` ở đây chỉ suy luận kiểu của **biến cục bộ**; chương trình vẫn được kiểm tra kiểu tại lúc biên dịch.

### Method reference phải phù hợp chức năng kiểm tra một đối số

| Biểu thức | Điều kiện kiểm tra |
| --- | --- |
| `String::isBlank` | Chuỗi rỗng hoặc chỉ gồm Java whitespace |
| `String::isEmpty` | Độ dài chuỗi bằng 0 |
| `Objects::isNull` | Đối số là `null` |
| `Objects::nonNull` | Đối số khác `null` |
| `s -> s.startsWith("tmp")` | Chuỗi bắt đầu bằng `tmp` |
| `s -> s.length() >= 5` | Độ dài ít nhất 5 UTF-16 code units |

Không thể dùng `String::startsWith` trực tiếp như một `Predicate<String>` kiểm tra prefix `"tmp"`: lời gọi `startsWith` còn cần đối số prefix. Hãy cố định nó bằng `s -> s.startsWith("tmp")`.

`Predicate.not` nhận `Predicate<? super T>`, không nhận trực tiếp một `Consumer<T>`, `Function<T,R>` hay `Supplier<Boolean>`. Method reference muốn sử dụng ở đây phải khớp chữ ký một predicate trả về boolean với một đối số.

## 5. Null: phủ định không làm method reference trở nên an toàn

Ví dụ sau **có thể ném NullPointerException** nếu `values` chứa phần tử `null`:

```java
values.stream().filter(Predicate.not(String::isBlank));
```

Vì `String::isBlank` là một instance method reference, khi receiver bằng `null`, chính lời gọi `isBlank()` thất bại. `Predicate.not` không có cơ chế thay receiver bằng chuỗi rỗng hoặc tự bỏ qua phần tử đó.

Cách lọc an toàn với danh sách có thể chứa null:

```java
values.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(Predicate.not(String::isBlank));
```

Đây là **một đoạn pipeline minh họa**; `values` phải là collection/stream nguồn phù hợp. Chú ý thứ tự: loại `null` trước khi gọi instance methods `strip` và `isBlank`.

### Ví dụ chạy độc lập: PredicateNotNullSafety.java

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PredicateNotNullSafety {
    public static void main(String[] args) {
        List<String> values = Arrays.asList(
                null, "  Java  ", "", " \t", null, "Spring");

        List<String> cleaned = values.stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(Predicate.not(String::isBlank))
                .collect(Collectors.toList());

        Predicate<String> present = Objects::nonNull;
        Predicate<String> safeNonBlank =
                present.and(Predicate.not(String::isBlank));

        Predicate<String> isNull = Predicate.not(Objects::nonNull);

        System.out.println(cleaned);
        System.out.println(safeNonBlank.test(null));
        System.out.println(safeNonBlank.test("Java"));
        System.out.println(isNull.test(null));

        try {
            values.stream()
                    .filter(Predicate.not(String::isBlank))
                    .count();
        } catch (NullPointerException ex) {
            System.out.println("NPE: null input");
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateNotNullSafety.java
java PredicateNotNullSafety
```

```text
[Java, Spring]
false
true
true
NPE: null input
```

`Predicate.and` đánh giá vế sau **chỉ khi** vế trước trả về `true` (*short-circuit*). Do đó `safeNonBlank.test(null)` là `false` mà không gọi `String.isBlank()` trên `null`.

Phân biệt:

- `Predicate.not(null)`: tham số **predicate gốc** bị null; lỗi xảy ra **khi tạo predicate phủ định**.
- `Predicate.not(String::isBlank).test(null)`: predicate gốc hợp lệ nhưng **dữ liệu** null; lỗi xảy ra **khi đánh giá**.

Phủ định `Objects::nonNull` tương đương về logic với `Objects::isNull`; khi chỉ muốn kiểm tra null, thường dùng trực tiếp `Objects::isNull` để mã dễ đọc hơn.

## 6. Ý nghĩa Predicate<? super T>: dùng predicate của kiểu cha

Dấu `? super T` trong chữ ký cho phép dùng một predicate kiểm tra kiểu cha của `T` để xây dựng `Predicate<T>`.

### Ví dụ chạy độc lập: PredicateSuperType.java

```java
import java.util.function.Predicate;

public class PredicateSuperType {
    public static void main(String[] args) {
        Predicate<CharSequence> emptySequence =
                sequence -> sequence.length() == 0;

        Predicate<String> nonEmptyString =
                Predicate.not(emptySequence);

        System.out.println(nonEmptyString.test("Java"));
        System.out.println(nonEmptyString.test(""));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateSuperType.java
java PredicateSuperType
```

```text
true
false
```

`String` triển khai `CharSequence`, nên predicate cho `CharSequence` có thể đánh giá một `String`. API cho phép sử dụng nó để tạo predicate phủ định dành cho chuỗi mà không phải ép kiểu.

## 7. Kết hợp and, or và phép phủ định

Các phương thức vẫn được hỗ trợ trên `Predicate<T>`:

- `p.and(q)` biểu diễn `p(x) && q(x)`, dừng sớm khi `p` trả `false`.
- `p.or(q)` biểu diễn `p(x) || q(x)`, dừng sớm khi `p` trả `true`.
- `p.negate()` hoặc `Predicate.not(p)` biểu diễn `!p(x)`.

Vị trí đặt phủ định thay đổi kết quả:

| Biểu thức | Phép logic |
| --- | --- |
| `Predicate.not(p.and(q))` | `!(p && q) = !p || !q` |
| `Predicate.not(p.or(q))` | `!(p || q) = !p && !q` |
| `Predicate.not(p).and(q)` | `!p && q` |
| `Predicate.not(p).and(Predicate.not(q))` | `!p && !q` |

Hai hàng đầu áp dụng định luật De Morgan. Đặc biệt `!(p && q)` **không** tương đương với `!p && !q`.

### Ví dụ chạy độc lập: PredicateComposition.java

```java
import java.util.function.Predicate;

public class PredicateComposition {
    public static void main(String[] args) {
        Predicate<String> startsWithApi =
                value -> value.startsWith("api");
        Predicate<String> atLeastFive =
                value -> value.length() >= 5;

        Predicate<String> notBoth =
                Predicate.not(startsWithApi.and(atLeastFive));

        Predicate<String> neither =
                Predicate.not(startsWithApi)
                        .and(Predicate.not(atLeastFive));

        System.out.println(notBoth.test("api"));
        System.out.println(neither.test("api"));
        System.out.println(notBoth.test("api42"));
        System.out.println(neither.test("xy"));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateComposition.java
java PredicateComposition
```

```text
true
false
false
true
```

`"api"` thỏa prefix nhưng chưa đủ 5 ký tự: `notBoth` trả `true`, `neither` trả `false`. `"api42"` thỏa cả hai nên `notBoth` trả `false`. `"xy"` không thỏa cả hai điều kiện, nên `neither` trả `true`.

Các predicate trong `and`/`or` được đánh giá theo thứ tự và dừng sớm theo hợp đồng API. Ngoại lệ từ predicate thực sự được gọi sẽ truyền ra ngoài. Khi có thể, giữ predicate không có side effect để logic không phụ thuộc vào số lần đánh giá hoặc cơ chế song song.

## 8. Cẩn thận: filter giữ phần tử, removeIf xóa phần tử

`Predicate.not` có thể dùng ở các API chấp nhận `Predicate<T>`, chẳng hạn `Stream.filter`, `Collection.removeIf`, `Stream.anyMatch`, `allMatch`, `noneMatch`. Tuy nhiên cách tiêu thụ predicate khác nhau.

Với danh sách `["", "Java", " "]`:

| Cách dùng | Kết quả |
| --- | --- |
| `stream().filter(Predicate.not(String::isBlank))` | Giữ `"Java"` trong Stream kết quả |
| `list.removeIf(String::isBlank)` | Xóa `""` và `" "` |
| `list.removeIf(Predicate.not(String::isBlank))` | Xóa `"Java"`, giữ hai chuỗi blank |

Với `removeIf`, `true` nghĩa là **xóa**. Đây không phải một phép lọc không thay đổi dữ liệu. Nếu dùng danh sách bất biến tạo bằng `List.of(...)`, thao tác xóa không được hỗ trợ; dùng `ArrayList` nếu thật sự muốn sửa danh sách.

### Ví dụ chạy độc lập: PredicateCollectionUse.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PredicateCollectionUse {
    public static void main(String[] args) {
        List<String> source = List.of("", "Java", " ", "Spring");

        List<String> filtered = source.stream()
                .filter(Predicate.not(String::isBlank))
                .collect(Collectors.toList());

        List<String> mutable = new ArrayList<>(source);
        mutable.removeIf(String::isBlank);

        List<String> opposite = new ArrayList<>(source);
        opposite.removeIf(Predicate.not(String::isBlank));

        System.out.println(filtered);
        System.out.println(mutable);
        System.out.println(opposite.size());
        System.out.println(opposite.get(0).isEmpty());
        System.out.println(opposite.get(1).isBlank());
        System.out.println(source.size());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateCollectionUse.java
java PredicateCollectionUse
```

```text
[Java, Spring]
[Java, Spring]
2
true
true
4
```

`filtered` và `mutable` cùng giữ “Java”, “Spring” theo hai cơ chế khác nhau. `opposite` còn hai phần tử blank, và danh sách `source` vẫn có bốn phần tử. Việc kiểm tra kích thước cùng `isEmpty`/`isBlank` tránh mơ hồ khi in những chuỗi trông giống khoảng trắng.

## 9. Không nhầm Predicate<T> với các primitive predicates

`IntPredicate`, `LongPredicate` và `DoublePredicate` là functional interfaces riêng cho các kiểu nguyên thủy. Không thể đưa chúng trực tiếp vào `Predicate.not` vì phương thức nhận `Predicate<? super T>`, không nhận `IntPredicate`.

```java
java.util.function.IntPredicate even = n -> n % 2 == 0;
java.util.function.IntPredicate odd = even.negate();
System.out.println(odd.test(3)); // true
```

Đây là đoạn minh họa hợp lệ trong một phương thức. Với `IntStream.filter(...)`, dùng `IntPredicate.negate()` hoặc lambda trả về boolean như `n -> n % 2 != 0`. Các API chuyên biệt giảm nhu cầu boxing, nhưng không có nghĩa `Predicate.not` tự chuyển đổi chúng.

## 10. Thực thi Stream: lazy, null và side effect

- `Stream.filter(...)` là thao tác trung gian *lazy*; predicate thường được gọi khi có terminal operation như `collect`, `count` hoặc `forEach`.
- Một đối tượng Stream được dùng cho một pipeline tiêu thụ; đừng tái sử dụng chính Stream đó sau terminal operation.
- Method reference giữ nguyên hành vi của phương thức gốc; nếu phương thức ném ngoại lệ, việc phủ định không bắt ngoại lệ.
- Với parallel stream, predicate nên không phụ thuộc vào trạng thái có thể thay đổi và không tạo side effect không được kiểm soát.
- Nếu xử lý dữ liệu có thể null hoặc dữ liệu Unicode phức tạp, xác định hợp đồng kiểm tra riêng trước khi chọn `String::isBlank` hay predicate tùy chỉnh.

## 11. Regression test: kiểm tra kết quả cụ thể

Ví dụ sau không cần thư viện ngoài, ném `AssertionError` nếu kết quả sai. Nó dùng hàm `check` vì từ khóa `assert` của Java có thể bị tắt nếu không bật `-ea`.

### PredicateNotRegression.java

```java
import java.util.Objects;
import java.util.function.Predicate;

public class PredicateNotRegression {
    private static int checks = 0;

    private static void check(String name, boolean expected, boolean actual) {
        checks++;
        if (expected != actual) {
            throw new AssertionError(name + ": expected="
                    + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        Predicate<String> nonBlank = Predicate.not(String::isBlank);
        check("empty", false, nonBlank.test(""));
        check("spaces", false, nonBlank.test("   "));
        check("tab", false, nonBlank.test("\t"));
        check("content", true, nonBlank.test("Java"));
        check("NBSP", true, nonBlank.test("\u00A0"));

        Predicate<String> nonEmpty = Predicate.not(String::isEmpty);
        check("blank but nonempty", true, nonEmpty.test(" "));

        Predicate<String> notTemp =
                Predicate.not(s -> s.startsWith("tmp"));
        check("other prefix", true, notTemp.test("report"));
        check("tmp prefix", false, notTemp.test("tmp-report"));

        Predicate<String> isNull = Predicate.not(Objects::nonNull);
        check("null", true, isNull.test(null));
        check("nonNull", false, isNull.test("x"));

        Predicate<String> startsApi = s -> s.startsWith("api");
        Predicate<String> longEnough = s -> s.length() >= 5;
        Predicate<String> notBoth =
                Predicate.not(startsApi.and(longEnough));
        Predicate<String> neither =
                Predicate.not(startsApi).and(Predicate.not(longEnough));

        check("notBoth", true, notBoth.test("api"));
        check("neither", false, neither.test("api"));

        System.out.println("PASS: " + checks + " assertions");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PredicateNotRegression.java
java PredicateNotRegression
```

```text
PASS: 12 assertions
```

Bộ test gồm 5 trường hợp blank, 1 trường hợp phân biệt empty/blank, 2 trường hợp prefix, 2 trường hợp null và 2 trường hợp kết hợp predicate: tổng 12 assertions. Khi đưa vào dự án, có thể chuyển các ca thành unit test JUnit theo phiên bản JUnit dự án đang hỗ trợ.

## 12. Sai lầm thường gặp và cách tự kiểm tra

1. **Nghĩ rằng `Predicate.not` tự kiểm tra null.** Nó chỉ phủ định boolean. Đối số null cho một instance method reference như `String::isBlank` vẫn có thể gây NPE.
2. **Dùng `isEmpty` thay `isBlank` tùy tiện.** Chuỗi `" \t"` khác rỗng nhưng blank; phủ định hai predicate cho kết quả khác.
3. **Viết `!String::isBlank` hoặc `String::isBlank.negate()`.** Đây là cú pháp sai; sử dụng `Predicate.not(String::isBlank)` hoặc biến `Predicate<String>` rồi gọi `negate()`.
4. **Nhầm nghĩa `true` trong `filter` và `removeIf`.** Một bên giữ phần tử, một bên xóa phần tử.
5. **Dùng sai định luật De Morgan.** `!(p && q)` tương đương `!p || !q`, không phải `!p && !q`.
6. **Đưa `IntPredicate` hoặc hàm không trả boolean vào `Predicate.not`.** Chọn đúng functional interface và phương thức phủ định.
7. **Bỏ qua target type.** Nếu suy luận generic phức tạp, viết kiểu `Predicate<T>` tường minh hoặc `Predicate.<T>not(...)`.
8. **Nghĩ rằng phủ định đã chuẩn hóa dữ liệu.** `Predicate.not` không trim, strip, thay đổi ký tự, đồng bộ dữ liệu hay xử lý ngoại lệ.

### Tự luyện

**A.** `List.of("", "Java", "  ").stream().filter(Predicate.not(String::isBlank))` giữ phần tử nào?

**B.** `Predicate.not(String::isBlank).test(null)` trả về `true` hay `false`?

**C.** `list.removeIf(Predicate.not(String::isBlank))` xóa những phần tử nào?

**D.** Nếu đã có `Predicate<String> valid`, có thể dùng `valid.negate()` thay `Predicate.not(valid)` không?

**E.** `Predicate.not(p.or(q))` có tương đương `Predicate.not(p).or(Predicate.not(q))` không?

**Đáp án:** A: chỉ `"Java"`. B: ném `NullPointerException`; không trả boolean. C: xóa phần tử **không blank**. D: có, theo hợp đồng API. E: không; đúng là `!p && !q`.

## Tài liệu chính thức

- [Java SE 11 — Predicate<T>: not, negate, and, or](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/function/Predicate.html).
- [Java SE 25 — Predicate<T> vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Predicate.html).
- [Java SE 11 — Stream.filter và các terminal operations](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 11 — String.isBlank, String.isEmpty, String.strip](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html).
- [Java SE 11 — Collection.removeIf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Collection.html).
