# Tham chiếu phương thức instance qua tên kiểu trong Java (TypeName::instanceMethod)

Trong Java, **method reference** cho phép dùng tên phương thức như một cách viết ngắn gọn cho lambda khi đã có một phương thức phù hợp với functional interface đích. Một dạng quan trọng là **tham chiếu phương thức instance thông qua tên kiểu**: `TypeName::instanceMethod` (còn gọi là *unbound instance method reference*, hay *tham chiếu instance chưa gắn với đối tượng cụ thể*).

Khác với `someObject::method`, dạng `String::length` **không cố định một đối tượng `String` ngay khi tạo method reference**. Thay vào đó, đối tượng sẽ được cung cấp **khi functional interface được gọi**. Trong trường hợp phương thức được chọn là phương thức instance, **tham số đầu tiên của phương thức trừu tượng duy nhất (SAM)** đóng vai trò *receiver*; các tham số SAM tiếp theo trở thành đối số thật của phương thức instance.

Ví dụ cốt lõi:

```java
Function<String, Integer> length = String::length;
int result = length.apply("Java"); // 4
```

Lời gọi `length.apply("Java")` có ý nghĩa tương đương `"Java".length()`. Đây là cú pháp từ Java 8 và vẫn còn hiệu lực trong Java hiện đại.

> **Ghi nhớ nhanh:** Với phương thức instance không có tham số `T::m`, functional interface cần có một tham số đầu tiên tương thích với receiver `T`. Với phương thức instance có `k` tham số, functional interface thường cần **`k + 1` tham số**: một receiver và `k` đối số. Quy tắc này áp dụng khi quá trình phân giải thực sự chọn phương thức instance; dạng `TypeName::method` cũng có thể tham chiếu phương thức `static` nếu ngữ cảnh phù hợp.

## 1. Cấu trúc cú pháp và vai trò receiver

Xét lớp `String` có phương thức instance `int length()`. Khi viết:

```java
Function<String, Integer> length = String::length;
```

Compiler nhìn vào **kiểu đích** `Function<String,Integer>`, với SAM `Integer apply(String value)`, và thấy rằng tham số `String` này có thể làm receiver cho `String.length()`. Vì `length()` trả `int`, Java có thể tự boxing kết quả thành `Integer` để phù hợp `Function`.

Dạng lambda tương đương về ý nghĩa:

```java
Function<String, Integer> length = value -> value.length();
```

Hai cách này đều tạo callback nhận **một `String`**, không tạo callback nhận số nguyên ngay lập tức. Phần thân chỉ được gọi khi thực hiện `apply`.

### 1.1. Công thức tổng quát

Nếu phương thức instance có dạng minh họa:

```java
R method(A arg1, B arg2)
```

Đây chỉ là **chữ ký mô tả**, không phải method có thể đặt độc lập vào tệp Java; `R`, `A` và `B` là các kiểu giả định.

Với unbound method reference `T::method`, một SAM tương thích sẽ có các tham số theo thứ tự:

```text
SAM:    (T receiver, A arg1, B arg2) -> R
Gọi:    receiver.method(arg1, arg2)
```

Vì vậy:

- Phương thức instance **không có đối số** thường ánh xạ sang `Function<T,R>` (hoặc `ToIntFunction<T>` nếu kết quả là `int`).
- Phương thức instance **có một đối số** thường ánh xạ sang `BiFunction<T,A,R>` hoặc `BiPredicate<T,A>` nếu trả `boolean`.
- Phương thức instance **có hai đối số** cần một functional interface có ba tham số phù hợp; `java.util.function` không có loại `TriFunction` tổng quát.
- Nếu phương thức instance **trả `void`**, SAM có thể chọn các loại như `Consumer<T>` (không có đối số ngoài receiver) hoặc `BiConsumer<T,A>` (một đối số ngoài receiver).

Chọn interface phải dựa vào **kiểu và số tham số thực tế**, không đếm mỗi số đối số đặt trong dấu ngoặc của phương thức instance rồi quên receiver.

### 1.2. Phân biệt ba dạng thường thấy

| Cách viết | Đối tượng receiver đến từ đâu? | Ví dụ với kiểu đích |
| --- | --- | --- |
| `TypeName::instanceMethod` | Tham số đầu tiên của SAM tại lúc gọi | `Function<String,Integer> f = String::length` |
| `expression::instanceMethod` | Giá trị của `expression` được xác định khi tạo tham chiếu | `Supplier<Integer> f = text::length` |
| `TypeName::staticMethod` | Không có receiver instance; SAM cung cấp các đối số của static method | `Function<String,Integer> f = Integer::parseInt` |

Các dạng cùng sử dụng dấu `::` nhưng có cơ chế khác nhau. Riêng bài này tập trung vào **trường hợp thứ nhất**, không đồng nhất nó với tham chiếu tới static method.

## 2. Ví dụ cơ bản: receiver xuất hiện tại lúc gọi

### 2.1. Không có đối số ngoài receiver: `String::trim`

```java
Function<String, String> trim = String::trim;

System.out.println(trim.apply("  Java  "));   // Java
System.out.println(trim.apply("  Lambda "));  // Lambda
```

Đoạn code minh họa cần `import java.util.function.Function;`. Mỗi lần gọi `apply`, chuỗi được truyền vào trở thành receiver cho `trim()`. Vì vậy, **cùng một** biến `trim` có thể dùng với nhiều chuỗi khác nhau.

Lambda tương đương:

```java
Function<String, String> trim = text -> text.trim();
```

Lưu ý API: `String.trim()` vẫn được hỗ trợ, nhưng nó dùng quy tắc khoảng trắng lịch sử theo ký tự không lớn hơn U+0020. Khi muốn loại bỏ khoảng trắng theo định nghĩa `Character.isWhitespace`, có thể cân nhắc `String.strip()` (Java 11+) tùy yêu cầu nghiệp vụ. Dạng unbound tương ứng là `String::strip`, với `Function<String,String>`. Không nên đánh đồng `trim` và `strip` trong mọi dữ liệu Unicode.

### 2.2. Một đối số ngoài receiver: `String::startsWith`

`String.startsWith(String prefix)` là phương thức instance nhận một `String` và trả `boolean`. Tham chiếu chưa gắn receiver cần **hai đối số ở SAM**:

```java
BiPredicate<String, String> startsWith = String::startsWith;

boolean ok = startsWith.test("Java Lambda", "Java"); // true
```

Tương đương:

```java
BiPredicate<String, String> startsWith =
        (text, prefix) -> text.startsWith(prefix);
```

Phân tích: tham số thứ nhất `"Java Lambda"` là receiver; tham số thứ hai `"Java"` là prefix được chuyển vào `startsWith(prefix)`. `BiPredicate` có SAM `boolean test(T first, U second)`, nên kiểu trả về primitive `boolean` là phù hợp.

### 2.3. Một đối số ngoài receiver, có kết quả khác: `String::substring`

`String.substring(int beginIndex)` nhận một chỉ số bắt đầu rồi trả `String`:

```java
BiFunction<String, Integer, String> suffix = String::substring;

String value = suffix.apply("lambda", 2); // mbda
```

Tương đương:

```java
BiFunction<String, Integer, String> suffix =
        (text, beginIndex) -> text.substring(beginIndex);
```

Ở đây `Integer` trong `BiFunction` được unboxing thành `int` cho `substring(int)`. Nếu chỉ số không hợp lệ, `StringIndexOutOfBoundsException` có thể phát sinh khi gọi `apply`.

Không thể gán đơn giản `String::substring` cho `Function<String,String>` để compiler tự tìm ra chỉ số bắt đầu; `String.substring` không có phiên bản không tham số. Nếu cần luôn cắt từ vị trí 2, lambda `text -> text.substring(2)` diễn đạt ý định đó tốt hơn.

### 2.4. Hai đối tượng cùng kiểu: `String::compareToIgnoreCase`

`String.compareToIgnoreCase(String anotherString)` trả giá trị `int` theo quy tắc so sánh của API. Có thể đưa vào `Comparator<String>` vì SAM `compare(a,b)` nhận hai chuỗi:

```java
Comparator<String> ignoreCase = String::compareToIgnoreCase;

int result = ignoreCase.compare("java", "JAVA"); // 0
```

Tương đương `(a,b) -> a.compareToIgnoreCase(b)`. `a` làm receiver, `b` là tham số truyền vào. Với trường hợp so sánh không phân biệt hoa thường đơn giản, `String.CASE_INSENSITIVE_ORDER` cũng là comparator có sẵn; chọn công cụ dễ đọc và phù hợp hợp đồng sắp xếp của ứng dụng.

Không nên suy đoán các phép so sánh chuỗi kiểu này đáp ứng mọi yêu cầu sắp xếp theo ngôn ngữ tự nhiên hoặc collation đặc thù. Khi cần quy tắc ngôn ngữ, cần thiết kế và kiểm tra chính sách locale tương ứng.

## 3. Interface và collection cũng có thể cung cấp unbound method reference

Tên kiểu trong `TypeName::instanceMethod` không nhất thiết là lớp concrete. Nó có thể là **interface** khai báo phương thức instance.

### 3.1. `List::size`

`List` khai báo `int size()`. Ta có thể viết:

```java
ToIntFunction<List<String>> count = List::size;

int n = count.applyAsInt(Arrays.asList("a", "b", "c")); // 3
```

Đoạn này cần import `List`, `Arrays`, `ToIntFunction`. `List::size` lấy `List<String>` được truyền vào làm receiver. `ToIntFunction<T>` có SAM `int applyAsInt(T value)`, tránh boxing kết quả thành `Integer` so với `Function<List<String>, Integer>`.

Việc dùng `List` ở bên trái dấu `::` giúp callback hoạt động với các implementation của `List` khi chúng đáp ứng hợp đồng này. Không cần biết receiver cụ thể là `ArrayList` hay implementation khác.

### 3.2. `CharSequence::length`

`CharSequence` là interface có phương thức instance `int length()`. Có thể dùng:

```java
ToIntFunction<CharSequence> length = CharSequence::length;

int n = length.applyAsInt(new StringBuilder("abcd")); // 4
```

Đây là một ví dụ quan trọng: **receiver không cần đúng bằng một lớp cụ thể được nhắc trong kiểu đích**; nó chỉ cần là đối tượng tương thích với kiểu interface mà phương thức được tham chiếu. `StringBuilder` implements `CharSequence` nên hoạt động bình thường.

### 3.3. `StringBuilder::append`: receiver bị biến đổi

`StringBuilder.append(String value)` trả về `StringBuilder`, nhưng cũng thay đổi nội dung đối tượng receiver. Ví dụ:

```java
BiConsumer<StringBuilder, String> append = StringBuilder::append;

StringBuilder builder = new StringBuilder("A");
append.accept(builder, "B");
// builder.toString() là "AB".
```

`BiConsumer.accept` có kết quả `void`; trong trường hợp này giá trị trả về của `append` được bỏ qua, còn tác dụng phụ lên `builder` vẫn xảy ra. **Method reference không biến phương thức có side effect thành hàm thuần**, không tự sao chép receiver, và không tự đồng bộ để dùng an toàn giữa các thread.

Lưu ý `StringBuilder` có nhiều overload của `append`; compiler chọn phương thức tương thích dựa trên SAM `(StringBuilder, String) -> void`. Ở trường hợp khác, overload có thể khiến code khó hiểu hoặc nhập nhằng, nên đôi khi lambda tường minh dễ bảo trì hơn.

## 4. Sơ đồ ánh xạ SAM và phương thức instance

Để tránh nhầm thứ tự, hãy ghi ra hai chữ ký:

```text
Phương thức instance:  R T.method(A value)
SAM cần tương thích:   R apply(T receiver, A value)

Gọi SAM:
  callback.apply(object, arg)

Có hiệu quả tương đương:
  object.method(arg)
```

So sánh nhanh:

| Method reference | Interface đích hợp lệ | Receiver | Đối số phương thức | Kết quả |
| --- | --- | --- | --- | --- |
| `String::length` | `Function<String,Integer>` | `String` tham số 1 | Không có | `Integer` (boxing từ `int`) |
| `String::isEmpty` | `Predicate<String>` | `String` tham số 1 | Không có | `boolean` |
| `String::trim` | `UnaryOperator<String>` | `String` tham số 1 | Không có | `String` |
| `String::startsWith` | `BiPredicate<String,String>` | `String` tham số 1 | Prefix tham số 2 | `boolean` |
| `String::substring` | `BiFunction<String,Integer,String>` | `String` tham số 1 | Index tham số 2 | `String` |
| `List::size` | `ToIntFunction<List<String>>` | `List<String>` tham số 1 | Không có | `int` |
| `String::compareToIgnoreCase` | `Comparator<String>` | `String` tham số 1 | Chuỗi tham số 2 | `int` |

Một phương thức instance đôi khi có thể được đưa vào SAM trả `void` dù phương thức thật có kết quả, **nếu kết quả bị bỏ đi** và ngữ cảnh cho phép, như `StringBuilder::append` với `BiConsumer`. Điều này không áp dụng một cách máy móc cho mọi kiểu dữ liệu hoặc mọi overload.

## 5. Unbound khác bound reference ở thời điểm gắn receiver

Xét hai callback:

```java
String text = "Java";

Supplier<Integer> bound = text::length;
Function<String, Integer> unbound = String::length;

int a = bound.get();          // 4
int b = unbound.apply("ABC"); // 3
```

**Bound reference `text::length`:**

- Receiver là đối tượng mà `text` đang tham chiếu **tại thời điểm tạo callback**.
- SAM `Supplier.get()` không cần tham số receiver.
- Những lần gọi sau tiếp tục dùng receiver đã giữ; với đối tượng mutable, nội dung của đối tượng có thể thay đổi, nhưng đó vẫn là cùng đối tượng được giữ.

**Unbound reference `String::length`:**

- Không cố định một chuỗi cụ thể trong callback.
- SAM `Function.apply(String text)` cung cấp receiver **mỗi lần gọi**.
- Có thể dùng một callback với nhiều chuỗi khác nhau.

### 5.1. So sánh tình huống null

Điểm khác biệt quan trọng là **thời điểm xảy ra lỗi nếu receiver bằng null**.

```java
Function<String, Integer> unbound = String::length;

try {
    unbound.apply(null); // Receiver null tại thời điểm gọi.
} catch (NullPointerException ex) {
    System.out.println("NPE khi gọi");
}
```

Với bound reference:

```java
String missing = null;

// Việc đánh giá biểu thức method reference này tự ném NPE.
// Supplier<Integer> invalid = missing::length;
```

**Bound method reference kiểm tra biểu thức receiver ngay khi tạo tham chiếu.** Trong khi đó `TypeName::instanceMethod` không có biểu thức receiver để kiểm tra lúc tạo; null receiver được phát hiện khi callback cố gọi phương thức instance. Cả hai không cung cấp cơ chế xử lý null tự động.

Đừng nhầm với `Function<String,String> f = s -> s == null ? "" : s.trim();`: lambda đó có logic xử lý null do người lập trình chủ động viết, không phải tính năng tự có của method reference.

## 6. Kiểu đích quyết định có biên dịch được không

Method reference là **poly expression**: nó cần ngữ cảnh xác định functional interface đích, chẳng hạn phép gán hoặc tham số phương thức. Bản thân `String::length` chưa tự mang một kiểu callback duy nhất.

Những ví dụ hợp lệ:

```java
Function<String, Integer> length = String::length;
ToIntFunction<String> primitiveLength = String::length;
Predicate<String> empty = String::isEmpty;
BiPredicate<String, String> startsWith = String::startsWith;
```

Cùng một phương thức instance có thể phù hợp với các SAM khác nhau nếu kiểu kết quả/boxing tương thích.

### 6.1. Lỗi thiếu tham số receiver

```java
// KHÔNG BIÊN DỊCH:
// Supplier<Integer> invalid = String::length;
```

`Supplier.get()` không có tham số, nhưng tham chiếu instance `String::length` cần một receiver. Cách sửa là dùng `Function<String,Integer>` để cung cấp receiver, hoặc gắn receiver sẵn bằng `someText::length` nếu đã có đối tượng cụ thể.

### 6.2. Lỗi thiếu tham số thật của phương thức

```java
// KHÔNG BIÊN DỊCH:
// Function<String, Boolean> invalid = String::startsWith;
```

`startsWith(prefix)` cần receiver và prefix, trong khi `Function.apply` chỉ có một tham số. Cách sửa:

```java
BiPredicate<String, String> check = String::startsWith;
```

Hoặc nếu muốn kiểm tra tiền tố cố định:

```java
Predicate<String> startsWithJava =
        text -> text.startsWith("Java");
```

Lambda giúp gắn một đối số không thay đổi; method reference unbound không tự cung cấp hằng `"Java"`.

### 6.3. Lỗi không tương thích kiểu trả về

```java
// KHÔNG BIÊN DỊCH:
// Function<String, String> invalid = String::length;
```

`String.length()` trả `int`; Java có thể boxing thành `Integer`, nhưng **không tự chuyển `int` thành `String`**. Nếu muốn chuỗi số:

```java
Function<String, String> sizeText =
        text -> Integer.toString(text.length());
```

Đừng chọn kiểu đích chỉ từ tên phương thức mà quên kiểm tra đầu ra và những chuyển đổi thực sự được Java cho phép.

### 6.4. Lỗi suy luận kiểu với `var`

`var` cho biến cục bộ có từ Java 10, nhưng nó không cung cấp target type rõ cho một method reference trần:

```java
// KHÔNG BIÊN DỊCH:
// var length = String::length;
```

Cách đúng:

```java
Function<String, Integer> length = String::length;
```

Không nhầm trường hợp này với cú pháp `(var x) -> ...` cho tham số lambda từ Java 11; cả hai thuộc các khái niệm khác nhau và không thay thế yêu cầu về target type cho method reference.

## 7. Overload: compiler chọn chữ ký dựa trên kiểu đích

Khi một tên phương thức có nhiều overload, compiler dùng tham số và kết quả của SAM đích để chọn phương thức phù hợp.

Ví dụ `String.substring` có ít nhất hai dạng:

```java
String substring(int beginIndex)
String substring(int beginIndex, int endIndex)
```

Vì `BiFunction<String,Integer,String>` có **hai tham số SAM** (receiver + một đối số), dạng thích hợp là `substring(int)`:

```java
BiFunction<String, Integer, String> suffix = String::substring;
String result = suffix.apply("Lambda", 2); // mbda
```

Nếu muốn dùng overload có **hai đối số** `substring(int,int)`, cần một SAM nhận **ba tham số**. JDK không có `TriFunction<T,U,V,R>` tổng quát, nhưng có thể định nghĩa một interface mang ý nghĩa hoặc cung cấp lambda gắn trước một chỉ số nếu nghiệp vụ cho phép.

Ví dụ interface với đủ ba tham số:

```java
@FunctionalInterface
interface SubstringRange {
    String take(String receiver, int begin, int end);
}

SubstringRange slice = String::substring;
String text = slice.take("Lambda", 1, 4); // amb
```

Đây là **đoạn mã minh họa đặt trong cùng một lớp/ngữ cảnh hợp lệ**; interface và lời gọi được dùng riêng, không phải chương trình tự biên dịch nếu đặt hai khai báo top-level cùng tệp theo định dạng thiếu lớp chứa.

### 7.1. Không phải `TypeName::method` nào cũng là unbound

Biểu thức `TypeName::method` được Java dùng cho cả tình huống phương thức `static` và phương thức instance. Ví dụ:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<String, Integer> size = String::length;
```

- `Integer::parseInt` tham chiếu phương thức `static` `parseInt(String)`: đối số SAM là tham số của static method, **không có receiver**.
- `String::length` tham chiếu phương thức instance `length()`: đối số SAM là receiver.

Trong kiểu có cả overload static và instance cùng tên, quá trình phân giải có thể phức tạp hoặc nhập nhằng. Java Language Specification (`15.13`) mô tả cách tìm phương thức cho biểu thức `ReferenceType::method` theo số tham số SAM, bao gồm khả năng phương thức static có `n` tham số hoặc phương thức instance có `n - 1` đối số ngoài receiver. **Không áp dụng thủ thuật “cứ thấy `Type::m` thì thêm receiver” nếu method được chọn là static.**

Nếu overload khó đọc, hãy chọn phương thức cụ thể hơn hoặc viết lambda tường minh để compiler và đồng đội thấy rõ receiver/đối số.

## 8. Tính đa hình: method reference không khóa implementation ở runtime

Unbound method reference có thể tham chiếu phương thức được khai báo ở **interface hoặc lớp cha**, nhưng implementation instance được gọi sẽ tuân theo quy tắc dispatch của Java.

Ví dụ:

```java
interface Label {
    String label();
}

class SimpleLabel implements Label {
    @Override
    public String label() {
        return "simple";
    }
}

class LoudLabel implements Label {
    @Override
    public String label() {
        return "LOUD";
    }
}

Function<Label, String> labeler = Label::label;

String a = labeler.apply(new SimpleLabel()); // simple
String b = labeler.apply(new LoudLabel());   // LOUD
```

Các khai báo trên minh họa cần import `Function` và đặt trong ngữ cảnh Java hợp lệ, ví dụ class chứa phương thức thực thi. `Label::label` có receiver kiểu `Label` trong SAM, nhưng khi gọi với `SimpleLabel` hay `LoudLabel`, Java thực thi implementation của đối tượng cụ thể.

Đây là polymorphism thông thường, không phải method reference tạo bản sao phương thức hoặc luôn gọi implementation của interface. Khi có overload, lựa chọn **chữ ký** diễn ra theo kiểu tĩnh và luật compiler; còn dispatch implementation của phương thức instance override diễn ra tại runtime theo quy tắc Java.

## 9. Chương trình Java hoàn chỉnh: kiểm chứng tất cả trường hợp chính

Tạo tệp **`UnboundMethodReferenceDemo.java`**. Chương trình dùng Java 8-compatible syntax/API, chạy được bằng JDK 17+ và giữ khả năng tương thích với Java 8; không phụ thuộc thư viện bên ngoài.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

public class UnboundMethodReferenceDemo {

    interface Label {
        String label();
    }

    static class SimpleLabel implements Label {
        @Override
        public String label() {
            return "simple";
        }
    }

    static class LoudLabel implements Label {
        @Override
        public String label() {
            return "LOUD";
        }
    }

    public static void main(String[] args) {
        Function<String, Integer> length = String::length;
        Function<String, String> trim = String::trim;
        Predicate<String> empty = String::isEmpty;

        System.out.println("length: " + length.apply("Java"));
        System.out.println("trim: " + trim.apply("  Lambda  "));
        System.out.println("empty: " + empty.test(""));

        BiPredicate<String, String> starts = String::startsWith;
        System.out.println("startsWith: "
                + starts.test("Java Lambda", "Java"));

        BiFunction<String, Integer, String> suffix =
                String::substring;
        System.out.println("substring: "
                + suffix.apply("lambda", 2));

        Comparator<String> ignoreCase =
                String::compareToIgnoreCase;
        System.out.println("compare: "
                + ignoreCase.compare("java", "JAVA"));

        ToIntFunction<List<String>> listSize = List::size;
        System.out.println("listSize: "
                + listSize.applyAsInt(
                        Arrays.asList("a", "b", "c")));

        BiConsumer<StringBuilder, String> append =
                StringBuilder::append;
        StringBuilder builder = new StringBuilder("A");
        append.accept(builder, "B");
        System.out.println("append: " + builder);

        Function<Label, String> getLabel = Label::label;
        System.out.println("simple: "
                + getLabel.apply(new SimpleLabel()));
        System.out.println("loud: "
                + getLabel.apply(new LoudLabel()));

        String fixedText = "Hello";
        Supplier<Integer> bound = fixedText::length;
        System.out.println("bound: " + bound.get());
        System.out.println("unbound: " + length.apply("ABC"));

        try {
            length.apply(null);
        } catch (NullPointerException ex) {
            System.out.println("null receiver: NPE");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UnboundMethodReferenceDemo.java
java UnboundMethodReferenceDemo
```

**Stdout chính xác của chương trình:**

```text
length: 4
trim: Lambda
empty: true
startsWith: true
substring: mbda
compare: 0
listSize: 3
append: AB
simple: simple
loud: LOUD
bound: 5
unbound: 3
null receiver: NPE
```

**Giải thích lần lượt:**

1. `String::length` lấy `"Java"` làm receiver và trả 4. `String::trim` cắt khoảng trắng ngoài của `"  Lambda  "`, còn `String::isEmpty` trả `true` với chuỗi rỗng.
2. `String::startsWith` dùng receiver `"Java Lambda"` và prefix `"Java"`; `String::substring` dùng receiver `"lambda"` và chỉ số 2 nên ra `"mbda"`.
3. `String::compareToIgnoreCase` trả 0 cho hai chuỗi `"java"` và `"JAVA"`.
4. `List::size` được áp dụng trên một danh sách có ba phần tử, cho 3. `StringBuilder::append` sửa receiver từ `"A"` thành `"AB"`.
5. `Label::label` gọi đúng implementation của từng đối tượng: `simple` hoặc `LOUD`.
6. `fixedText::length` có receiver gắn trước nên `Supplier.get()` trả 5; `String::length` unbound nhận receiver mới `"ABC"` ở `Function.apply` nên trả 3.
7. `length.apply(null)` ném `NullPointerException` trong lúc gọi instance method; khối `catch` in một dòng xác định mà không phụ thuộc thông điệp ngoại lệ giữa các phiên bản JDK.

Không có code nào thực hiện I/O hoặc kết nối bên ngoài, nên stdout trên ổn định theo dữ liệu cố định.

## 10. Sử dụng unbound reference với Stream và collection

Dạng `TypeName::instanceMethod` đặc biệt hữu dụng khi thao tác mỗi phần tử của collection. Chẳng hạn:

```java
List<String> source = Arrays.asList("Java", "Lambda", "API");

List<Integer> lengths = source.stream()
        .map(String::length)
        .collect(Collectors.toList());
```

Giả định đã import `List`, `Arrays` và `Collectors`. Stream `map` yêu cầu `Function<? super String, ? extends Integer>`. Với mỗi phần tử, `String::length` nhận **chính phần tử đó làm receiver**. `lengths` lần lượt có `[4, 6, 3]`.

Một ví dụ không cần tạo `Function` thành biến:

```java
List<String> nonEmpty = source.stream()
        .filter(((Predicate<String>) String::isEmpty).negate())
        .collect(Collectors.toList());
```

Ở đây `String::isEmpty` là unbound method reference tương thích với `Predicate<String>`. Việc ép kiểu chỉ để gọi phương thức `negate()` trực tiếp trên callback; đoạn dễ đọc hơn là:

```java
Predicate<String> empty = String::isEmpty;
List<String> nonEmpty = source.stream()
        .filter(empty.negate())
        .collect(Collectors.toList());
```

Phương thức `filter` nhận predicate, nên khi cần lọc “không rỗng”, có thể viết `s -> !s.isEmpty()` thay vì ép kiểu nếu chỉ dùng một lần.

### 10.1. Method reference không làm thay đổi bản chất Stream

Các thao tác trung gian như `map` và `filter` thường có tính lazy. `String::length` không chạy trên phần tử ngay khi bạn chỉ thiết lập bước `map(String::length)`; nó được gọi khi pipeline được thực thi, thường bởi thao tác kết thúc như `collect`.

Trường hợp Stream parallel hoặc pipeline có side effect, các quy tắc về thứ tự và đồng bộ của Stream vẫn phải được tuân thủ. Unbound reference chỉ xác định **cách gọi một phương thức trên receiver**, không tự bảo đảm thread safety.

## 11. Checked exception và hợp đồng SAM

Method reference không bỏ qua kiểm tra checked exception. Giả sử bạn có class với phương thức instance khai báo:

```java
import java.io.IOException;

class FileLoader {
    String load() throws IOException {
        throw new IOException("Ví dụ lỗi I/O");
    }
}
```

Đây là lớp minh họa độc lập về chữ ký, không bắt buộc chạy để hiểu quy tắc.

Interface riêng có thể cho phép checked exception:

```java
@FunctionalInterface
interface IOOperation<T, R> {
    R run(T receiver) throws IOException;
}
```

Tham chiếu sau hợp lệ nếu đặt các kiểu vào cùng ngữ cảnh truy cập phù hợp:

```java
IOOperation<FileLoader, String> operation = FileLoader::load;
```

Nhưng `Function<FileLoader,String>` **không có `throws IOException` trên `apply`**, nên dòng sau sẽ **không biên dịch**:

```java
// KHÔNG BIÊN DỊCH:
// Function<FileLoader, String> wrong = FileLoader::load;
```

Lý do là kiểm tra checked exception của SAM đích; việc tham chiếu qua tên kiểu không làm thay đổi hợp đồng `throws`. Nếu API bắt buộc dùng `Function`, cần một lambda tự xử lý ngoại lệ hoặc một adapter chuyển lỗi có ý nghĩa và giữ nguyên nguyên nhân (ví dụ `UncheckedIOException` cho `IOException`) thay vì coi method reference là cơ chế “né” compiler.

## 12. Những lỗi thiết kế và hiểu nhầm hay gặp

| Hiểu nhầm / lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `String::length` là gọi static method | `length()` là instance method; receiver đến từ SAM | Nghĩ tương đương `s -> s.length()` |
| `Supplier<Integer> f = String::length` | SAM không có tham số receiver | Dùng `Function<String,Integer>` hoặc một đối tượng `text::length` |
| `Function<String,Boolean> f = String::startsWith` | Thiếu prefix sau receiver | Dùng `BiPredicate<String,String>` hoặc lambda gắn prefix |
| `Function<String,String> f = String::length` | Kiểu kết quả không tương thích | Chọn `Function<String,Integer>` hoặc tự chuyển số thành chuỗi |
| Nghĩ `Type::method` luôn thêm receiver | Nếu method được chọn là static, không có receiver | Đối chiếu chữ ký và ngữ cảnh SAM |
| Nghĩ method reference được gọi ngay lúc khai báo | Nó tạo callback, không lập tức chạy method | Chỉ khi thực thi SAM mới gọi phương thức |
| Tưởng `String::length` cố định một chuỗi | Unbound reference không gắn sẵn đối tượng | Truyền receiver mới ở mỗi lần `apply` |
| Truyền null làm receiver và mong tự xử lý | Instance invocation trên null ném `NPE` | Có chính sách null rõ ràng hoặc dùng lambda có kiểm tra |
| Quên overload của method | Compiler phải chọn chữ ký tương thích SAM | Viết rõ target type, dùng lambda khi cần |
| Không để ý side effect | Instance method có thể sửa trạng thái receiver | Kiểm soát trạng thái, concurrency và contract |
| Dùng method reference với checked exception không phù hợp | Method reference cũng tuân thủ `throws` của SAM | Bắt lỗi hoặc thiết kế callback có hợp đồng phù hợp |
| Thử `var f = String::length` | Method reference trần không có target type để suy luận | Khai báo functional interface rõ ràng |

### Vì sao lambda đôi khi tốt hơn method reference?

Method reference không phải mục tiêu tự thân. Nếu callback cần **kiểm tra đầu vào**, **gắn giá trị cố định**, **biến đổi thêm kết quả**, **bắt ngoại lệ** hoặc đơn giản làm rõ tham số nào là receiver, lambda thường dễ đọc hơn:

```java
Predicate<String> startsWithJava =
        text -> text != null && text.startsWith("Java");
```

`String::startsWith` không thể thay thế hoàn toàn lambda này vì predicate chỉ có một tham số và cần kiểm tra null cùng một prefix cố định.

Dùng `TypeName::instanceMethod` khi nó phản ánh một lời gọi instance trực tiếp, rõ ràng và tương thích hoàn toàn với functional interface đích.

## 13. Checklist trước khi áp dụng

1. Phương thức sau `::` **thực sự là instance method** trong overload được chọn chưa?
2. Kiểu SAM có **tham số đầu tiên** tương thích để làm receiver không?
3. Các tham số SAM tiếp theo có khớp số lượng/thứ tự/kiểu đối số instance method không?
4. Kiểu trả về có phù hợp SAM, kể cả boxing/unboxing hoặc bỏ kết quả với SAM `void`, không?
5. Receiver có thể `null` không và lỗi cần được xử lý ở đâu?
6. Method có overload hoặc generic khiến việc chọn target method khó hiểu không?
7. Callback có thể ném checked exception mà SAM không cho phép không?
8. Có side effect hoặc dữ liệu mutable cần lưu ý khi chạy song song không?
9. Nếu dùng với Stream, bạn có hiểu lazy evaluation và thời điểm invoke không?
10. Nếu lambda tường minh giúp đọc đúng ý hơn, có nên chọn lambda thay method reference không?

**Kết luận:** `TypeName::instanceMethod` là cách viết ngắn của một callback mà **receiver được cung cấp khi gọi**, thông thường là tham số đầu tiên của SAM. Nó khác `object::instanceMethod` (receiver gắn sẵn) và `TypeName::staticMethod` (không có receiver). Dạng này vẫn được dùng phổ biến với `Function`, `Predicate`, `BiFunction`, `BiPredicate`, `Comparator`, các interface primitive và Stream trên các JDK hiện nay.

## Tài liệu tham khảo

- Java Language Specification, **`15.13 — Method Reference Expressions** (Java SE 25): https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13
- Java Language Specification, **`15.13.3 — Run-Time Evaluation of Method References**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13.3
- Java SE API, **`java.util.function`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html
- Java SE API, **`java.lang.String`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html
