# Tham chiếu phương thức đối tượng qua tên kiểu trong Java

## 1. Khái niệm và mục đích

**Tham chiếu phương thức đối tượng qua tên kiểu** (reference to an instance method of an arbitrary object of a particular type) có dạng:

```java
TypeName::instanceMethod
```

Ví dụ: `String::trim`, `String::length`, `String::startsWith`, `String::compareToIgnoreCase` và `List<String>::size`. Đây là **method reference không gắn sẵn với một đối tượng cụ thể** (*unbound instance method reference*). Đối tượng nhận lệnh gọi (receiver) được cung cấp khi phương thức của functional interface được thực thi.

```java
Function<String, String> trimText = String::trim;
String result = trimText.apply("  Java  "); // "Java"
```

Trong lời gọi `trimText.apply(...)`, đối số `"  Java  "` đóng vai trò receiver của `trim()`. Java thực hiện lời gọi tương đương `"  Java  ".trim()`. Biểu thức `String::trim` tự nó **không gọi** `trim()` ngay khi được tạo.

Tính năng này xuất hiện từ Java 8, thường dùng với `Function`, `Predicate`, `BiPredicate`, `Comparator`, các functional interface tự định nghĩa và pipeline Stream. Mục tiêu là diễn tả thao tác “hãy gọi phương thức này trên đối tượng được truyền vào” một cách ngắn gọn khi thao tác đã có sẵn dưới dạng method.

## 2. Cách ánh xạ tham số: receiver đứng đầu

Về mặt ý tưởng, khi method instance có khai báo:

```java
ResultType instanceMethod(Arg1 a, Arg2 b);
```

thì tham chiếu `TypeName::instanceMethod` có thể phù hợp với phương thức trừu tượng đơn (SAM) nhận lần lượt:

1. Một receiver thuộc `TypeName` hoặc một kiểu tham chiếu phù hợp.
2. Các đối số `Arg1`, `Arg2` mà instance method cần.
3. Giá trị trả về tương thích với `ResultType` (theo các quy tắc chuyển đổi của Java).

Sơ đồ ánh xạ:

```text
SAM.apply(receiver, arg1, arg2)
          │         │     │
          ▼         ▼     ▼
       receiver.instanceMethod(arg1, arg2)
```

Ví dụ cùng một cú pháp nhưng số tham số SAM thay đổi theo chữ ký method:

| Method reference | Kiểu đích phù hợp | Lambda tương đương |
| --- | --- | --- |
| `String::length` | `ToIntFunction<String>` | `s -> s.length()` |
| `String::trim` | `Function<String, String>` | `s -> s.trim()` |
| `String::isEmpty` | `Predicate<String>` | `s -> s.isEmpty()` |
| `String::startsWith` | `BiPredicate<String, String>` | `(s, prefix) -> s.startsWith(prefix)` |
| `String::equalsIgnoreCase` | `BiPredicate<String, String>` | `(a, b) -> a.equalsIgnoreCase(b)` |
| `String::compareToIgnoreCase` | `Comparator<String>` | `(a, b) -> a.compareToIgnoreCase(b)` |

Đọc ví dụ `String::startsWith`: method `startsWith(String prefix)` có **một** tham số trong khai báo, nhưng `BiPredicate.test(String, String)` có **hai** tham số: `s` làm receiver, `prefix` truyền vào method. Receiver không phải tham số thứ nhất trong khai báo `startsWith`; nó là đối tượng đứng trước dấu chấm khi gọi method.

**Lưu ý:** Số tham số và kiểu trả về phải được đối chiếu với *functional interface đích*. Không thể suy ra toàn bộ chữ ký chỉ bằng cách nhìn `TypeName::methodName`, nhất là khi method được overload.

## 3. Ví dụ Java 17+ có thể biên dịch, chạy độc lập

Tạo file `UnboundMethodReferenceDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class UnboundMethodReferenceDemo {
    public static void main(String[] args) {
        Function<String, String> trimText = String::trim;
        ToIntFunction<String> countCharacters = String::length;
        BiPredicate<String, String> hasPrefix = String::startsWith;
        BiPredicate<String, String> sameIgnoringCase =
                String::equalsIgnoreCase;
        Comparator<String> compareIgnoringCase =
                String::compareToIgnoreCase;

        System.out.println("trim=" + trimText.apply("  Java  "));
        System.out.println("length=" + countCharacters.applyAsInt("lambda"));
        System.out.println("prefix=" + hasPrefix.test("functional", "func"));
        System.out.println("equal=" + sameIgnoringCase.test("JAVA", "java"));
        System.out.println("compare=" + compareIgnoringCase.compare("api", "API"));

        List<String> words = List.of(" Java ", " API ");
        List<String> normalized = words.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .toList();
        System.out.println("words=" + normalized);
    }
}
```

Biên dịch và chạy:

```bash
javac UnboundMethodReferenceDemo.java
java UnboundMethodReferenceDemo
```

Kết quả stdout:

```text
trim=Java
length=6
prefix=true
equal=true
compare=0
words=[java, api]
```

Giải thích:

- `trimText.apply("  Java  ")` gọi `trim()` trên chuỗi được truyền vào; kết quả không chứa khoảng trắng đầu/cuối.
- `countCharacters.applyAsInt("lambda")` gọi `length()` trên `"lambda"` và trả về giá trị `int` bằng 6. `ToIntFunction` tránh boxing sang `Integer` so với `Function<String, Integer>`.
- `hasPrefix.test("functional", "func")` là lời gọi tương đương `"functional".startsWith("func")`.
- `sameIgnoringCase.test("JAVA", "java")` kiểm tra hai chuỗi không phân biệt chữ hoa/thường.
- `Comparator<String>` có SAM `compare(a, b)`, nên `String::compareToIgnoreCase` gọi `a.compareToIgnoreCase(b)`.
- Mỗi phần tử Stream lần lượt trở thành receiver của `trim()` rồi `toLowerCase()`; các thao tác `map` chạy khi terminal operation `toList()` được thực hiện.

## 4. So sánh với các dạng method reference khác

| Dạng | Ví dụ | Receiver lấy từ đâu? |
| --- | --- | --- |
| `TypeName::instanceMethod` | `String::length` | Đối số đầu tiên khi gọi SAM |
| `objectExpression::instanceMethod` | `text::length` | Đối tượng `text` đã được chỉ định lúc tạo reference |
| `TypeName::staticMethod` | `Integer::parseInt` | Không có receiver; mọi đối số SAM đi thẳng vào static method |
| `TypeName::new` | `ArrayList::new` | Không phải method call; tạo đối tượng mới |

Ví dụ đối chiếu:

```java
String text = "Java";

java.util.function.ToIntFunction<String> unbound = String::length;
java.util.function.IntSupplier bound = text::length;

System.out.println(unbound.applyAsInt("Hello")); // 5
System.out.println(bound.getAsInt());             // 4
```

`String::length` chờ nhận một chuỗi bất kỳ khi gọi `applyAsInt`; `text::length` đã gắn với chính biến `text` (đối tượng mà biểu thức `text` đánh giá ra tại thời điểm tạo reference) và vì thế `IntSupplier.getAsInt()` không cần tham số. Hai phương thức `applyAsInt` và `getAsInt` thuộc **hai functional interface khác nhau**.

Đừng lẫn `String::length` với `String.length()`; latter không phải cú pháp hợp lệ để gọi một method instance chỉ dựa trên tên lớp. Khi cần gọi trực tiếp, phải có receiver, chẳng hạn `"Java".length()`.

## 5. Kiểu đích (target typing), overload và kiểu tổng quát

Method reference là một biểu thức phụ thuộc vào ngữ cảnh kiểu đích. Trình biên dịch dùng SAM để chọn method phù hợp trong các phiên bản overload, xác minh kiểu receiver/đối số, kiểu trả về và ngoại lệ checked.

Ví dụ `String.substring` có các overload nhận một hoặc hai số nguyên. Dưới đây SAM có **hai** đối số tổng cộng (`String`, `Integer`), nên overload `substring(int beginIndex)` được chọn:

```java
java.util.function.BiFunction<String, Integer, String> fromIndex =
        String::substring;

System.out.println(fromIndex.apply("functional", 4)); // tional
```

Nếu muốn dùng `substring(int beginIndex, int endIndex)` qua kiểu `String::substring`, SAM cần ba đối số tổng cộng: receiver và hai chỉ số. Có thể khai báo functional interface ba tham số tùy ý để diễn đạt trường hợp đó; `BiFunction` chỉ đủ cho receiver cộng một đối số.

Tham chiếu tới method của kiểu generic cũng tuân theo nguyên tắc này:

```java
java.util.function.ToIntFunction<java.util.List<String>> listSize =
        java.util.List<String>::size;

System.out.println(listSize.applyAsInt(java.util.List.of("A", "B"))); // 2
```

Ở ví dụ trên, receiver có kiểu `List<String>` và `size()` không cần đối số ngoài receiver.

Một ví dụ cho tính đa hình:

```java
java.util.function.ToIntFunction<CharSequence> sequenceLength =
        CharSequence::length;

System.out.println(sequenceLength.applyAsInt("Java"));                  // 4
System.out.println(sequenceLength.applyAsInt(new StringBuilder("ABC"))); // 3
```

`CharSequence::length` sử dụng lời gọi instance được dispatch theo đối tượng thực tế. `String` và `StringBuilder` đều triển khai `CharSequence`, nên cùng một method reference làm việc với cả hai.

Một method reference đứng riêng không có “kiểu hàm” tự suy luận tùy ý trong Java. Ví dụ `var f = String::length;` **không biên dịch** vì thiếu functional interface đích để xác định chữ ký. Hãy dùng `ToIntFunction<String> f = String::length;` hoặc truyền trực tiếp vào API có tham số SAM rõ ràng.

## 6. Các tình huống áp dụng

### Chuyển đổi và lọc phần tử trong Stream

```java
List<String> names = List.of(" Lan ", "", " Minh ");
List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(java.util.function.Predicate.not(String::isEmpty))
        .toList();
// cleaned: [Lan, Minh]
```

Ở `map`, mỗi chuỗi là receiver của `trim()`. Ở `filter`, chuỗi sau khi cắt khoảng trắng là receiver của `isEmpty()`. `Predicate.not(...)` đảo điều kiện để bỏ chuỗi rỗng. Đoạn này minh họa và giả định đã import `java.util.List`.

### Sắp xếp theo thuộc tính hoặc so sánh trực tiếp

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
Comparator<String> insensitive = String::compareToIgnoreCase;

List<String> items = List.of("pear", "a", "banana");
System.out.println(items.stream().sorted(byLength).toList());
// [a, pear, banana]
```

`comparingInt` cần một hàm trích xuất khóa `int`; `String::length` phù hợp vì nó nhận receiver `String` và trả về `int`. `Comparator<String>` cần hai đối số nên `String::compareToIgnoreCase` cũng phù hợp, nhưng với vai trò so sánh hai đối tượng.

### Phân tách receiver và đối số nghiệp vụ

```java
BiPredicate<String, String> containsText = String::contains;

System.out.println(containsText.test("method reference", "reference")); // true
```

Lời gọi ở đây tương đương `"method reference".contains("reference")`. Cách viết này hữu ích khi cả receiver và tham số method đều được cung cấp vào thời điểm gọi.

## 7. Lỗi thường gặp và cách tránh

**1. Nhầm số tham số của SAM.** Đối với `TypeName::instanceMethod`, phải tính receiver như tham số **đầu tiên** của SAM:

```java
// Sai: startsWith(String) cần cả receiver lẫn prefix.
// Predicate<String> p = String::startsWith;

// Đúng:
BiPredicate<String, String> p = String::startsWith;
System.out.println(p.test("Java", "Ja")); // true
```

**2. Nhầm tham chiếu qua tên kiểu với tham chiếu tới đối tượng cố định.** `String::toUpperCase` phù hợp với `Function<String, String>`; `"Java"::toUpperCase` phù hợp với `Supplier<String>` vì không cần tham số receiver ở SAM.

**3. Quên kiểm tra null.** Trong tham chiếu không gắn receiver, nếu đối số receiver đầu tiên bằng `null`, lúc thực thi Java sẽ thất bại với `NullPointerException`:

```java
ToIntFunction<String> f = String::length;
// f.applyAsInt(null); // Ném NullPointerException khi gọi.
```

Việc tạo `f` không tự truy cập một receiver. Nếu dữ liệu có thể null, cần lọc/kiểm tra hoặc dùng lambda có chính sách null rõ ràng, ví dụ `s -> s == null ? 0 : s.length()`.

**4. Nghĩ `::` luôn thay thế được mọi lambda.** Method reference chỉ phù hợp nếu chữ ký SAM tương thích. Nếu phải đổi thứ tự tham số, thêm điều kiện, xử lý null hoặc thực hiện nhiều bước, lambda tường minh thường dễ hiểu hơn:

```java
BiPredicate<String, String> beginsWith =
        (prefix, text) -> text.startsWith(prefix);
```

Đoạn này cố ý nhận `prefix` trước rồi mới đến `text`; không thể thay trực tiếp bằng `String::startsWith`, vì dạng đó nhận `text` trước.

**5. Bỏ qua overload, kiểu trả về và checked exception.** Hai method trùng tên có thể khác số/kiểu đối số; Java chọn theo kiểu đích. SAM cũng phải chấp nhận kiểu trả về (hoặc cho phép bỏ kết quả trong ngữ cảnh `void`) và quy tắc checked exception. Khi lỗi biên dịch khó hiểu, viết lại thành lambda có kiểu tham số rõ ràng để nhìn thấy lời gọi thực tế.

**6. Gọi nhầm method tĩnh hoặc constructor.** `Integer::parseInt` không có receiver; `ArrayList::new` tạo object. Không nên áp dụng quy tắc “tham số đầu là receiver” cho mọi biểu thức `TypeName::member` khi member được chọn là static method.

## 8. Quy trình xác định một tham chiếu có hợp lệ hay không

1. Xác định method instance cần dùng và chữ ký cụ thể, kể cả các overload.
2. Chọn functional interface có đúng kiểu kết quả; nếu kết quả là primitive, cân nhắc `ToIntFunction`, `ToLongFunction`, `ToDoubleFunction` để tránh boxing.
3. Xếp receiver làm tham số đầu của SAM, rồi xếp các tham số method theo đúng thứ tự.
4. Kiểm tra khả năng truy cập method, tính tương thích kiểu, overload và checked exception.
5. Đổi sang lambda tương đương để tự kiểm tra: `TypeName::m` → `(receiver, args...) -> receiver.m(args...)`.
6. Kiểm tra dữ liệu receiver có thể null, cùng thời điểm thực thi (đặc biệt trong Stream).

## 9. Bài tập tự kiểm tra

1. Hãy khai báo một `BiPredicate<String, String>` dùng `String::endsWith` và thử `test("Report.java", ".java")`.
2. Với `String::charAt`, hãy tìm functional interface chuẩn phù hợp để nhận receiver và chỉ số, rồi trả về `Character`.
3. Vì sao `ToIntFunction<String> f = String::length;` hợp lệ, còn `IntSupplier f = String::length;` không hợp lệ?

**Gợi ý/đáp án:** (1) `BiPredicate<String, String> ends = String::endsWith;`, cho kết quả `true`. (2) `BiFunction<String, Integer, Character> charAt = String::charAt;`; Java boxing từ `char` sang `Character` và unboxing `Integer` sang `int`. (3) `String::length` dạng không gắn receiver cần một đối số `String` trong SAM, nhưng `IntSupplier.getAsInt()` không có tham số.

Điểm cần nhớ: với **tham chiếu phương thức đối tượng qua tên kiểu**, đối tượng nhận lệnh gọi được truyền vào **đầu tiên** khi functional interface chạy. Cứ viết lambda tương đương `receiver -> receiver.method()` (hoặc `(receiver, arg) -> receiver.method(arg)`) là có thể kiểm tra đúng nghĩa, số tham số và thứ tự dữ liệu.
