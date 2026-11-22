# Kiểm tra với Java compiler — Thực hành tổng hợp Pattern Matching

## 1. Vì sao cần kiểm tra với compiler, không chỉ đọc code?

Trong thực hành Java Pattern Matching, một đoạn mã có thể **trông đúng** nhưng thực tế không biên dịch vì phiên bản Java chưa hỗ trợ cú pháp, phạm vi biến pattern sai, `switch expression` thiếu case, case bị nhánh trước bao phủ hoặc generic type không kiểm tra được tại runtime.

Ngược lại, code **biên dịch thành công** vẫn có thể sai logic: `when` xét sai điều kiện, null record component được xử lý không đúng, nhánh fallback trả giá trị ngoài mong đợi. Vì vậy một bài kiểm tra đầy đủ phải có **hai cổng**:

1. **Compile-time check:** Compiler `javac` xác nhận cú pháp, hệ kiểu, phạm vi biến, exhaustiveness, domination và điều kiện sử dụng tính năng ngôn ngữ.
2. **Runtime test:** Chạy chương trình với các dữ liệu chủ động chọn; assertions xác nhận kết quả và ngoại lệ đúng theo hợp đồng nghiệp vụ.

Bài “**Kiểm tra với Java compiler**” thuộc nhóm **Thực hành tổng hợp**. Mục tiêu không phải chỉ học vài câu lệnh terminal, mà là biết **viết, biên dịch, giải thích lỗi, sửa code, chạy lại và bảo vệ kết quả bằng tests**.

Sau bài này, bạn sẽ thực hành:

- Xác định phiên bản `java`, `javac`, source/release và runtime thực sự.
- Biên dịch type patterns trong `instanceof` bằng Java 17 và record/switch patterns bằng Java 21.
- Phân tích các lỗi điển hình: **non-exhaustive switch, dominated case, flow scope, record pattern arity, generic type erasure**.
- Dùng các đoạn **cố ý không biên dịch** để kiểm tra compiler phát hiện đúng nhóm lỗi, không đưa chúng vào bản build sản phẩm.
- Viết chương trình Java 21 hoàn chỉnh, chạy **16 assertions** để kiểm tra cả nhánh match, guard false, null, nested record và fallback.
- Biết tích hợp `javac`/Maven/Gradle vào quá trình CI mà không nhầm warning với error hoặc compile success với application correctness.

**Phiên bản dùng trong bài:** Type pattern cho `instanceof` chính thức từ **Java 16 (JEP 394)**. Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) chính thức từ **Java 21**. Ví dụ chính dùng **Java 21 ổn định, không cần `--enable-preview`**.

## 2. Trước khi sửa lỗi: xác định đúng Java compiler và release

Trong một máy có nhiều JDK, lệnh `java` dùng để **chạy** chương trình và lệnh `javac` dùng để **biên dịch** không nhất thiết đến từ cùng một bản cài đặt. IDE, Maven, Gradle và CI còn có thể chọn toolchain khác terminal hiện tại.

Bắt đầu bằng:

```bash
java -version
javac -version
```

Kết quả phụ thuộc JDK trên máy, vì vậy **không có một stdout cố định** cho hai lệnh trên. Chúng cho biết runtime/Java compiler được shell chọn, không tự chứng minh IDE hoặc build system cũng đang dùng phiên bản ấy.

Kiểm tra xem compiler hỗ trợ target release nào:

```bash
javac --help
```

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `javac --release 17` | Biên dịch theo mức ngôn ngữ, API chuẩn và class-file target phù hợp Java 17 mà compiler hiện tại hỗ trợ. |
| `javac --release 21` | Biên dịch theo mức ngôn ngữ/API Java 21; cần JDK compiler có khả năng target Java 21. |
| `javac -d out ...` | Ghi các `.class` vào thư mục `out` thay vì trộn với source; hữu ích cho một ví dụ CLI. |
| `javac -Xlint:all` | Bật thêm các nhóm **cảnh báo** có hỗ trợ; không thay thế các kiểm tra bắt buộc của compiler. |
| `javac -Werror` | Coi các warning được phát ra là lỗi build; không cần thiết để bắt lỗi cú pháp hoặc non-exhaustive switch. |
| `--enable-preview` | Cho phép tính năng preview ở **release phù hợp với compiler**; không phải công tắc bật mọi tính năng Java tương lai. |

**Quan trọng:** Dùng JDK 21/24 để chạy `javac --release 17` vẫn có nghĩa là source phải hợp lệ theo **Java 17**, không được dùng record patterns final Java 21. Ngược lại, JDK 17 không hiểu target `--release 21` và thường báo lỗi tương đương “release version 21 not supported”.

Cũng không thể biên dịch class file target Java 21 rồi chạy trực tiếp bằng Java 17. Runtime quá cũ có thể báo `UnsupportedClassVersionError` vì không hỗ trợ phiên bản class file, ngay cả khi mã nguồn đã biên dịch thành công ở môi trường khác.

### 2.1. Source, compile và runtime là ba khâu khác nhau

1. **Source compatibility:** cú pháp có hợp lệ ở release mục tiêu không?
2. **Binary/API compatibility:** các class/API mà chương trình sử dụng có phù hợp release target và dependencies không?
3. **Runtime behavior:** chương trình chạy trên JVM dự kiến có cho kết quả đúng không?

Compiler chỉ giải quyết phần có thể kiểm tra tĩnh. Với pattern matching, Java biết quan hệ kiểu và cấu trúc case; nhưng không biết giá trị nghiệp vụ nào là “hợp lệ” nếu bạn không mã hóa ràng buộc vào Java.

## 3. Nhớ mốc Java để không chẩn đoán sai compiler

| Tính năng | Mốc chuẩn / preview | Cách hiểu khi build |
| --- | --- | --- |
| `record` class | Chính thức **Java 16**, JEP 395 | Java 17 tạo và truy cập record bình thường. |
| `instanceof String text` | Chính thức **Java 16**, JEP 394 | Java 17 dùng được, không cần preview. |
| Record pattern `Point(var x, var y)` | Preview Java 19 (JEP 405); second preview Java 20 (JEP 432); **final Java 21** (JEP 440) | Java 17 không hỗ trợ; Java 21 dùng thẳng. |
| Pattern matching for `switch` | Preview từ Java 17; **final Java 21**, JEP 441 | `case String s`, `when` và pattern switch Java 21 không cần preview. |
| Unnamed pattern `_` | Preview Java 21 (JEP 443); **final Java 22** (JEP 456) | Không dùng `_` như tính năng chuẩn khi target Java 21. |

Ví dụ đơn giản: có record không chứng minh đã có record deconstruction. Java 17 biên dịch được:

```java
record Point(int x, int y) {}

static int readX(Object input) {
    if (input instanceof Point point) {
        return point.x();
    }
    return -1;
}
```

Nhưng nếu dùng `input instanceof Point(var x, var y)` ở source level 17 thì compiler từ chối, vì đây là **record pattern** Java 21. Giải pháp là đổi source level lên 21 hoặc giữ type pattern với accessor; không nên thêm `--enable-preview` cho Java 17 rồi kỳ vọng tính năng ra đời ở Java 19/21 tự xuất hiện.

## 4. Quy trình kiểm tra một file Java từ đầu đến cuối

Khi có tệp `CompilerPatternCheckDemo.java` ở mục 9, dùng:

```bash
javac --release 21 CompilerPatternCheckDemo.java
java CompilerPatternCheckDemo
```

Dòng đầu kiểm tra tính hợp lệ của mã Java 21 và tạo các class file nếu thành công. Dòng thứ hai chạy `main` và thực hiện assertions. Nếu biên dịch lỗi, **không** coi bản `.class` cũ còn sót là kết quả của bản source mới. Có thể dùng thư mục output riêng để dễ quan sát:

```bash
javac --release 21 -d out CompilerPatternCheckDemo.java
java -cp out CompilerPatternCheckDemo
```

Điều kiện: tạo thư mục `out` phù hợp trước khi biên dịch nếu cần theo môi trường chạy. Khi dùng `-d out`, các class được đặt dưới output path, và lệnh `java -cp out ...` chạy đúng kết quả mới được build. Tránh chạy nhầm class cũ ở working directory.

### 4.1. Mã lỗi của tiến trình biên dịch

Trong quy trình build, điều quan trọng là **kiểm tra lệnh `javac` có kết thúc thành công không**. Trên shell Unix-like:

```bash
javac --release 21 CompilerPatternCheckDemo.java
echo $?
```

Lệnh `echo $?` in mã thoát của command trước. **`0`** thể hiện thành công; mã khác 0 nghĩa là lệnh báo lỗi. Câu lệnh trên chỉ minh họa cách kiểm tra trạng thái; khi dùng CI, tốt hơn để build thất bại trực tiếp thay vì chỉ in mã lỗi rồi tiếp tục.

Trong Windows PowerShell, dùng biến `$LASTEXITCODE` cho native process như `javac`; đừng sao chép cú pháp `$?` của Bash sang PowerShell và cho rằng ngữ nghĩa hoàn toàn giống nhau.

### 4.2. Hiểu diagnostic của javac

Một diagnostic thường gồm:

- Đường dẫn tệp và dòng/column gần vị trí lỗi.
- **Loại lỗi** như không tìm thấy biến, không tương thích kiểu, thiếu case, dominated case.
- Trích một phần dòng code và dấu chỉ vị trí.

Thông báo cụ thể thay đổi theo phiên bản compiler và cách tổ chức source. Vì vậy phần “Lỗi thường gặp” dưới đây đưa ra **ý nghĩa và ví dụ** thay vì yêu cầu bạn so khớp từng ký tự của error message.

## 5. Compiler kiểm tra type pattern và phạm vi biến như thế nào?

Type pattern ràng buộc biến **chỉ tại vị trí Java xác định pattern đã khớp**.

Ví dụ hợp lệ từ Java 16:

```java
static String describe(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    return "other";
}
```

Tại vế phải của `&&`, Java biết `input instanceof String text` đã đúng. Nếu input là `null`, `Integer` hoặc một `String` trắng, biểu thức điều kiện cho kết quả false và code trả `"other"`.

### 5.1. Lỗi biến pattern dùng ngoài flow scope

Ví dụ **cố ý sai**, nên đặt trong class thử nghiệm riêng:

```java
// KHÔNG BIÊN DỊCH trong class Java thông thường:
static int invalidScope(Object input) {
    if (input instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

Sau `if`, chương trình có thể đã đi qua nhánh **không khớp**, vì vậy biến `text` không chắc được ràng buộc. Compiler không cho phép dùng nó tại `return`.

Sửa bằng guard clause:

```java
static int safeLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Tại dòng cuối, mọi đường đi có pattern false đã kết thúc bằng `return -1`, nên compiler biết `text` tồn tại.

### 5.2. Vì sao đổi && thành || có thể khiến mã không biên dịch?

```java
// KHÔNG BIÊN DỊCH:
if (input instanceof String text || text.length() > 3) {
    System.out.println(text);
}
```

Khi vế trái false, `||` mới xem vế phải, nhưng pattern không khớp nên `text` chưa được ràng buộc. Cách viết `&&` phù hợp nếu vế phải cần biến pattern.

### 5.3. Biểu thức đã có kiểu tĩnh chính xác

Với biến kiểu tĩnh `String`, không cần pattern tự kiểm tra lại cùng kiểu. Một số kiểu kiểm tra dư thừa như `String s; s instanceof String text` bị Java từ chối vì kiểu biểu thức đã là subtype của kiểu pattern. Hãy dùng trực tiếp biến `s` và xử lý null theo hợp đồng nếu cần, thay vì chèn pattern vào mọi nơi.

**Kết luận:** Compiler kiểm tra **phạm vi và hệ kiểu**, không khẳng định logic sau khi khớp (ví dụ `isBlank()` phải true hay false) phù hợp nghiệp vụ. Phần đó cần test runtime.

## 6. Compiler kiểm tra record patterns ở Java 21

Khai báo:

```java
record Point(int x, int y) {}
```

Record pattern hợp lệ trên Java 21:

```java
static int sum(Object input) {
    if (input instanceof Point(var x, var y)) {
        return x + y;
    }
    return 0;
}
```

Từ khai báo record, compiler biết `Point` có **hai component** kiểu `int`. Nó kiểm tra danh sách nested patterns có đúng số lượng và kiểu thích hợp.

### 6.1. Sai số lượng component

```java
// KHÔNG BIÊN DỊCH: Point có hai component, nhưng pattern chỉ có một.
static int wrongArity(Object value) {
    return switch (value) {
        case Point(var x) -> x;
        default -> 0;
    };
}
```

Java 21 phát hiện lỗi tương đương **“incorrect number of nested patterns”** hoặc sai số component. Không phải vì đầu vào runtime thiếu dữ liệu: record `Point` đã xác định cấu trúc ở compile time.

Sửa:

```java
static int corrected(Object value) {
    return switch (value) {
        case Point(var x, var y) -> x;
        default -> 0;
    };
}
```

Bạn có thể không dùng `y`; vẫn phải có pattern cho vị trí thứ hai khi target Java 21 không dùng unnamed pattern preview. Java 22 đã chuẩn hóa unnamed pattern `_`, nhưng không nên đưa `_` vào source target 21 mặc định.

### 6.2. Nested record pattern và null

Ví dụ:

```java
record Amount(int cents, String currency) {}
record Payment(String id, Amount amount) {}
```

Pattern:

```java
// Snippet Java 21 trong một switch với selector Object:
case Payment(var id, Amount(var cents, var currency)) -> ...
```

Nó chỉ khớp khi selector là `Payment` và component `amount` là một record `Amount` **khác null**. Tuy nhiên `currency` vẫn có thể null vì `var currency` chỉ ràng buộc component String theo kiểu, **không tự yêu cầu non-null**.

Nếu `amount == null`, nested `Amount(...)` không khớp; bạn cần nhánh fallback trên `Payment` nếu muốn xử lý rõ:

```java
case Payment(var id, var amount) -> "missing-amount";
```

Compiler kiểm tra cấu trúc pattern, còn **validation của cents và currency** phải nằm trong guard, constructor, domain service hoặc tests tùy thiết kế. Mục 9 minh họa cả hai tầng này.

## 7. Compiler kiểm tra tính đầy đủ của switch và thứ tự case

### 7.1. Exhaustiveness: sealed interface giúp tìm nhánh bị thiếu

Giả sử:

```java
sealed interface Message permits Text, Payment, Quit {}
record Text(String value) implements Message {}
record Amount(int cents, String currency) {}
record Payment(String id, Amount amount) implements Message {}
record Quit() implements Message {}
```

Một `switch expression` trên `Message` cần bao phủ các subtype `Text`, `Payment` và `Quit` (hoặc dùng nhánh bao quát). Ví dụ sau **cố ý sai**:

```java
// KHÔNG BIÊN DỊCH: thiếu Payment và Quit.
static String incomplete(Message message) {
    return switch (message) {
        case Text(var value) -> "text";
    };
}
```

Compiler báo lỗi kiểu **“the switch expression does not cover all possible input values”**. Nếu thêm `Quit` mà vẫn quên `Payment`, lỗi chưa được giải quyết.

Cách sửa để giữ ưu điểm static checking là liệt kê đủ case **không thêm default vô điều kiện**:

```java
static String classifyMessage(Message message) {
    return switch (message) {
        case Text(var value) -> "text";
        case Payment(var id, var amount) -> "payment";
        case Quit() -> "quit";
    };
}
```

Trong snippet này selector null có thể ném `NullPointerException` vì không có `case null`. Tính exhaustive đối với kiểu không đồng nghĩa tự định nghĩa hành vi null. Nếu muốn trả một mã rõ ràng, thêm `case null -> "missing";`.

### 7.2. Guard when không bao phủ hết một subtype

```java
// KHÔNG BIÊN DỊCH: Text(null) hoặc Text(" ") không có nhánh.
static String guardOnly(Message message) {
    return switch (message) {
        case Text(var value) when value != null && !value.isBlank()
                -> "text:" + value;
        case Payment(var id, var amount) -> "payment";
        case Quit() -> "quit";
    };
}
```

Dù đã liệt kê tên ba subtype, nhánh `Text` có guard chỉ xử lý **một phần** Text. Vì vậy compiler không thể chứng minh exhaustiveness. Sửa bằng nhánh `Text` không guard **sau** nhánh có guard:

```java
case Text(var value) when value != null && !value.isBlank()
        -> "text:" + value.strip();
case Text(var value) -> "empty-text";
```

Điều này cũng giúp mã thể hiện rõ chính sách cho String null hoặc trắng. Trong ví dụ chính, pattern guard và fallback được kết hợp như vậy.

### 7.3. Domination: case rộng che case hẹp

```java
// KHÔNG BIÊN DỊCH: String bị CharSequence phía trước bao phủ.
static String dominated(Object input) {
    return switch (input) {
        case CharSequence chars -> "chars";
        case String text -> "text";
        default -> "other";
    };
}
```

Mọi `String` đều là `CharSequence`, nên case `String` ở sau bị compiler báo **dominated case label**. Cách sửa là đặt case hẹp trước:

```java
static String ordered(Object input) {
    return switch (input) {
        case String text -> "text";
        case CharSequence chars -> "chars";
        default -> "other";
    };
}
```

**Không nhầm hai loại lỗi:**

- **Non-exhaustive:** còn giá trị hợp lệ không có case.
- **Dominated:** có case bị case trước bao phủ nên không thể được chọn.

Một nhánh `default` không tự giải quyết domination. Bạn phải sửa thứ tự hoặc bỏ nhánh dư.

### 7.4. Switch expression khác switch statement truyền thống

Trong Java 21, **switch expression** và các **enhanced switch statements** phải exhaustive. Nhưng một **traditional switch statement** trên enum vẫn có thể thiếu vài case và biên dịch được theo quy tắc tương thích ngược. Ví dụ:

```java
enum Status { NEW, ACTIVE, DONE }

static void printStatus(Status value) {
    switch (value) {
        case NEW -> System.out.println("new");
        case ACTIVE -> System.out.println("active");
        // Không có DONE; traditional switch statement vẫn có thể biên dịch.
    }
}
```

Đừng kết luận mọi `switch (...) { case ... -> ... }` đều được compiler buộc exhaustive: ký hiệu `->` không quyết định nó là expression hay statement. Nếu muốn compiler hỗ trợ phát hiện thiếu enum case, hãy cân nhắc dùng `switch expression` trả giá trị, hoặc quy tắc static analysis/test bổ sung cho statement.

## 8. Generic type erasure: vì sao List<String> không phải type pattern thông thường?

Đây là lỗi thường thấy khi chuyển cast thủ công sang type patterns.

```java
// KHÔNG BIÊN DỊCH nếu raw có kiểu Object.
static int invalidGeneric(Object raw) {
    return raw instanceof java.util.List<String> names
            ? names.size()
            : 0;
}
```

Compiler có thể báo `java.lang.Object cannot be safely cast to java.util.List<java.lang.String>` hoặc một diagnostic về kiểu không thể kiểm tra an toàn. Do **type erasure**, khi runtime nhận một `List` thông thường, nó không lưu đầy đủ type argument `String` trong đối tượng để `instanceof` xác nhận.

Cách đúng cho đầu vào Object:

```java
static int countStrings(Object raw) {
    if (!(raw instanceof java.util.List<?> values)) return 0;

    int count = 0;
    for (Object value : values) {
        if (value instanceof String text) {
            count++;
        }
    }
    return count;
}
```

Ở đây compiler kiểm tra `List<?>` và biến `values` có kiểu danh sách wildcard; mỗi phần tử được kiểm tra bằng type pattern riêng. Một `List<Integer>` vẫn khớp `List<?>` nhưng không có phần tử nào khớp String.

**Đừng giải quyết bằng unchecked cast rồi tắt warning.** Nếu type của phần tử không được bảo đảm, ép sang `List<String>` có thể chuyển rủi ro lỗi sang một điểm sử dụng phần tử sau đó. Hãy validate dữ liệu tại ranh giới hệ thống.

## 9. Chương trình Java 21 hoàn chỉnh: vừa được compiler chấp nhận, vừa có 16 test

Tạo file **`CompilerPatternCheckDemo.java`** với toàn bộ nội dung sau:

```java
public class CompilerPatternCheckDemo {
    sealed interface Message permits Text, Payment, Quit {}
    record Text(String value) implements Message {}
    record Amount(int cents, String currency) {}
    record Payment(String id, Amount amount) implements Message {}
    record Quit() implements Message {}

    static String dispatch(Message message) {
        return switch (message) {
            case null -> "null-message";

            case Text(var value) when value != null && !value.isBlank()
                    -> "text:" + value.strip();
            case Text(var value) -> "empty-text";

            case Payment(var id, Amount(var cents, var currency))
                    when cents > 0 && currency != null && !currency.isBlank()
                    -> "payment:" + id + ":" + cents + ":" + currency;
            case Payment(var id, Amount(var cents, var currency))
                    -> "invalid-payment";
            case Payment(var id, var amount) -> "missing-amount";

            case Quit() -> "quit";
        };
    }

    static String classify(Object input) {
        if (input instanceof String value && !value.isBlank()) {
            return "string:" + value.strip();
        }
        if (input instanceof Integer number) {
            return "integer:" + number;
        }
        return input == null ? "null-value" : "other";
    }

    static int checks;

    static void expect(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + " expected " + expected + ", actual " + actual
            );
        }
        checks++;
        System.out.println("PASS " + name + " => " + actual);
    }

    public static void main(String[] args) {
        expect("text", "text:hello",
                dispatch(new Text(" hello ")));
        expect("text-blank", "empty-text",
                dispatch(new Text("  ")));
        expect("text-null", "empty-text",
                dispatch(new Text(null)));

        expect("payment", "payment:P1:250:USD",
                dispatch(new Payment("P1", new Amount(250, "USD"))));
        expect("payment-zero", "invalid-payment",
                dispatch(new Payment("P2", new Amount(0, "USD"))));
        expect("payment-negative", "invalid-payment",
                dispatch(new Payment("P3", new Amount(-10, "USD"))));
        expect("payment-null-currency", "invalid-payment",
                dispatch(new Payment("P4", new Amount(100, null))));
        expect("payment-blank-currency", "invalid-payment",
                dispatch(new Payment("P5", new Amount(100, " "))));
        expect("payment-null-amount", "missing-amount",
                dispatch(new Payment("P6", null)));

        expect("quit", "quit", dispatch(new Quit()));
        expect("null-message", "null-message", dispatch(null));

        expect("string", "string:Java", classify(" Java "));
        expect("blank-string", "other", classify("   "));
        expect("integer", "integer:7", classify(7));
        expect("long", "other", classify(7L));
        expect("null-value", "null-value", classify(null));

        System.out.println("checks=" + checks);
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 CompilerPatternCheckDemo.java
java CompilerPatternCheckDemo
```

**Stdout chính xác:**

```text
PASS text => text:hello
PASS text-blank => empty-text
PASS text-null => empty-text
PASS payment => payment:P1:250:USD
PASS payment-zero => invalid-payment
PASS payment-negative => invalid-payment
PASS payment-null-currency => invalid-payment
PASS payment-blank-currency => invalid-payment
PASS payment-null-amount => missing-amount
PASS quit => quit
PASS null-message => null-message
PASS string => string:Java
PASS blank-string => other
PASS integer => integer:7
PASS long => other
PASS null-value => null-value
checks=16
```

### 9.1. Mã này vượt qua kiểm tra static nào?

- `sealed interface Message` có ba loại `Text`, `Payment` và `Quit`. Các nhánh tổng quát cuối cùng của mỗi loại làm `switch expression` **exhaustive** mà không cần default.
- Case `Text(var value) when ...` đứng trước `case Text(var value)` để tránh case rộng che case hẹp.
- Case `Payment(... Amount(...)) when ...` đứng trước case nested `Payment(... Amount(...))` không guard. Case `Payment(var id, var amount)` cuối cùng bao phủ Payment có amount null và các trường hợp còn lại.
- Cấu trúc record pattern có đúng số component: `Payment` có hai và `Amount` có hai.
- Biến pattern `value`/`id`/`cents`/`currency` chỉ được sử dụng trong scope hợp lệ.
- `case null` xử lý null selector tường minh.
- `classify` kết hợp `instanceof String value && ...` nên vế phải chỉ sử dụng `value` sau khi pattern match.

### 9.2. Compiler chưa chứng minh điều gì?

Compiler không thể tự kết luận rằng `250` cents hợp lệ và `0` cents không hợp lệ theo nghiệp vụ. Nó cũng không biết `currency` có thể rỗng, hoặc việc trả `"invalid-payment"` là kết quả mong muốn. Do đó 16 assertions kiểm tra cả **giá trị hợp lệ và biên**.

Ví dụ `new Payment("P6", null)` không match nested `Amount(...)` nên vào case Payment còn lại. Trái lại, `new Payment("P4", new Amount(100, null))` match nested record nhưng guard false; case nested không guard xử lý thành `invalid-payment`. Hai trường hợp này chỉ khác nhau ở một tầng null, rất dễ bị bỏ sót nếu chỉ kiểm tra happy path.

Trong `classify`, `"   "` đúng là String nhưng guard false, nên kết quả `other`. Còn `7L` là Long, không khớp `Integer` và cũng vào `other`. Compiler bảo đảm đường điều khiển hợp lệ; test bảo đảm **đúng kết quả** cho dữ liệu đã chọn.

### 9.3. Assertions không cần thư viện test bên ngoài

Hàm `expect` so sánh `expected` với `actual`. Nếu không bằng nhau, nó ném `AssertionError` và chương trình không chạy hết các phép thử. Việc in `PASS` chỉ xuất hiện sau khi so sánh thành công.

Dòng `checks=16` có nghĩa **16 phép thử của ví dụ đã qua**, không có nghĩa bao phủ mọi giá trị đầu vào Java hay mọi quy tắc nghiệp vụ. Trong dự án lớn, chuyển các test này sang JUnit 5 hoặc framework test hiện có, thêm kiểm thử tương tác và dữ liệu biên theo yêu cầu sản phẩm.

## 10. Bộ lỗi compile-time để tự thực hành

Đây là một bài thực hành quan trọng: hãy **dự đoán lý do compiler từ chối**, sau đó sửa lại. Các đoạn cố ý sai **không nằm trong file chạy được của mục 9**. Nếu bạn đưa chúng vào cùng source folder rồi chạy build bình thường, build sẽ thất bại theo thiết kế.

| Đoạn lỗi | Kết quả compiler mong đợi | Cách sửa |
| --- | --- | --- |
| Chỉ có `case Text` khi selector là `Message` sealed | Switch expression không exhaustive | Thêm Payment và Quit hoặc fallback có chủ đích. |
| `case Text(...) when ...` mà không có nhánh Text khác | Guard false bỏ sót Text | Thêm case Text không guard sau nhánh đặc thù. |
| `case CharSequence` trước `case String` | String case bị dominated | Đặt String trước CharSequence. |
| `Point(var x)` cho `record Point(int x,int y)` | Sai arity nested patterns | Dùng hai component pattern. |
| `raw instanceof List<String> names` với raw Object | Không thể kiểm tra generic type argument an toàn | Dùng `List<?>` rồi kiểm tra từng phần tử. |
| `return text.length()` sau `if (raw instanceof String text) {...}` | Biến pattern không nằm trong scope được bảo đảm | Guard clause phủ định và early return. |
| Record deconstruction ở `--release 17` | Cú pháp không hỗ trợ source level 17 | Dùng type pattern + accessor hoặc nâng source 21. |

### 10.1. Cách tổ chức negative compilation tests

Nếu muốn kiểm tra compiler như một dạng unit test, đặt **mỗi snippet cố ý sai** vào một fixture riêng hoặc một bước test compilation-negative. Mục tiêu của test đó là **mong compiler từ chối**, không phải mong chương trình chạy được.

Ví dụ quy trình khái niệm trên shell Unix-like:

```bash
# BadSwitch.java là fixture cố ý sai, không thuộc main source.
if javac --release 21 BadSwitch.java; then
    echo "FAIL: compiler unexpectedly accepted BadSwitch.java"
    exit 1
else
    echo "PASS: compiler rejected BadSwitch.java"
fi
```

Ví dụ này chỉ xác nhận compiler trả mã lỗi khác 0. Nếu cần khẳng định *đúng nguyên nhân* (không phải lỗi typo hoặc thiếu import), nên kiểm tra **loại diagnostic**, vị trí và cấu trúc fixture. Không nên phụ thuộc tuyệt đối vào từng từ của thông báo vì nó có thể thay đổi theo phiên bản JDK.

**Đừng trộn fixture cố ý không biên dịch vào `src/main/java` hoặc `src/test/java` trong một build thông thường.** Nếu làm vậy, cả pipeline sẽ liên tục đỏ ngay cả khi code sản phẩm đúng. Hãy tạo job/check riêng khi nhóm thực sự cần compile-negative tests.

## 11. Các lệnh đối chiếu Java 17 và Java 21

### 11.1. Type patterns cho instanceof trên Java 17

Tệp nhỏ **`TypePattern17.java`**:

```java
public class TypePattern17 {
    static String parse(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "text:" + text.strip();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(parse(" java "));
        System.out.println(parse(7));
        System.out.println(parse(null));
    }
}
```

Lệnh:

```bash
javac --release 17 TypePattern17.java
java TypePattern17
```

Kết quả:

```text
text:java
other
other
```

Đây là bài đối chiếu nhỏ để chứng minh type pattern với `instanceof` **không đòi Java 21**. Các phương thức `strip()` và `isBlank()` đã có trong các bản Java phù hợp trước Java 17.

### 11.2. Record deconstruction không hợp lệ ở release 17

Dù project có record `Point`, đoạn:

```java
// KHÔNG BIÊN DỊCH ở --release 17:
record Point(int x, int y) {}

static int first(Object input) {
    if (input instanceof Point(var x, var y)) return x;
    return -1;
}
```

sẽ bị compiler từ chối với thông báo tương đương **“deconstruction patterns are not supported in -source 17”**. Trường hợp này không phải vấn đề `Point` thiếu constructor hay classpath hỏng: đơn giản là **Java 17 chưa có record patterns**.

Sửa tương thích 17:

```java
static int first(Object input) {
    if (input instanceof Point point) return point.x();
    return -1;
}
```

Nếu project nâng lên Java 21, dùng `Point(var x, var y)` như tính năng chuẩn. Không áp dụng cờ preview Java 21 cho source level 17; compiler không dùng preview để “quay ngược” tính năng đến một release trước khi nó ra đời.

## 12. Tích hợp compiler check vào Maven, Gradle và CI

### 12.1. Maven Compiler Plugin với Java 21

Với một Maven Java project đã cấu hình plugin thích hợp và chạy bằng JDK hỗ trợ 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Trong CI, dùng lệnh build có bước compile và test, ví dụ:

```bash
mvn clean verify
```

Nếu code có pattern switch thiếu case hoặc lỗi flow scoping, compiler làm bước build thất bại. Nếu code biên dịch thành công nhưng assertion sai, bước test sẽ thất bại. Hai nguồn lỗi nên được báo riêng để chẩn đoán đúng.

### 12.2. Gradle Groovy DSL

Ví dụ cấu hình toolchain Java 21 trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Trong project có Gradle Wrapper, ưu tiên lệnh wrapper phù hợp hệ điều hành:

```bash
./gradlew clean test
```

Trên Windows, dùng `gradlew.bat clean test` khi áp dụng. Các đoạn trên là cấu hình minh họa, không phải tệp build hoàn chỉnh; phiên bản Maven/Gradle/plugin phải hỗ trợ JDK 21 và test runner thực tế.

### 12.3. CI tối thiểu nên chứng minh điều gì?

Một pipeline tốt cần:

1. **Kiểm tra toolchain:** phiên bản compiler, source/release và runtime phù hợp.
2. **Biên dịch mã chính:** ngăn cú pháp sai, kiểu không hợp lệ, non-exhaustive switch, dominated cases.
3. **Biên dịch tests:** không để lỗi test source bị bỏ qua.
4. **Chạy tests:** so sánh expected/actual, kiểm tra null, guard true/false, fallback, ngoại lệ.
5. **Chạy lint/static analysis bổ sung khi có giá trị:** IDE inspections, Error Prone, PMD, Checkstyle hoặc SpotBugs có thể phát hiện lớp lỗi riêng tùy phiên bản hỗ trợ Java 21.
6. **Báo thất bại đúng khâu:** lỗi compile khác test failure, khác lỗi runtime/dependency/environment.

Một warning không nhất thiết làm build thất bại nếu chưa dùng `-Werror`; một compile error bắt buộc làm `javac` thất bại. Đừng thay đổi tiêu chuẩn build bằng cách bỏ `-Werror` hoặc tắt tests mà không đánh giá ảnh hưởng.

**Giới hạn công cụ:** Static analysis bên ngoài có thể hữu ích, nhưng `javac` vẫn là trọng tài cú pháp và quy tắc ngôn ngữ ở mức release bạn chọn. Không có chuyện một linter biến đoạn Java 17 không hỗ trợ record pattern thành mã hợp lệ.

## 13. Những hiểu nhầm hay gặp khi đọc thông báo lỗi

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `invalid source release: 21` | `javac` quá cũ cho target 21 | Chọn JDK compiler/toolchain hỗ trợ Java 21. |
| `deconstruction patterns not supported in source 17` | Dùng record pattern Java 21 ở release 17 | Giữ type pattern với accessor hoặc nâng release. |
| `switch expression does not cover all possible input values` | Thiếu subtype hoặc guard chỉ bao phủ một phần | Liệt kê case không guard phù hợp hoặc fallback có chủ đích. |
| `case label is dominated` | Nhánh rộng đứng trước nhánh hẹp | Đổi thứ tự case hoặc bỏ nhánh dư. |
| `cannot find symbol: text` sau `instanceof` | Biến pattern bị dùng ngoài flow scope | Dùng guard clause/early return hoặc đặt code trong nhánh đúng. |
| `incorrect number of nested patterns` | Record pattern không đủ/thừa component | Đối chiếu khai báo record và số vị trí pattern. |
| `Object cannot be safely cast to List<String>` | Erasure làm generic type không reifiable ở tình huống này | Dùng `List<?>` và validate element. |
| `NullPointerException` khi chạy switch | Selector null không có xử lý rõ hoặc code nhánh dereference component null | Bổ sung `case null`/guard theo hợp đồng; test null từng tầng. |
| `ClassCastException` khi chạy code cast cũ | Cast trực tiếp không được type check bảo vệ | Type pattern + non-match path hoặc báo lỗi rõ. |
| `UnsupportedClassVersionError` khi chạy | Runtime cũ hơn bytecode được compiler tạo | Đồng bộ target/runtime hoặc biên dịch theo release thấp hơn nếu source tương thích. |
| Code chạy trong IDE nhưng CI không biên dịch | IDE và CI chọn source level/JDK khác | So sánh toolchain, `--release` và cấu hình build. |
| Code biên dịch nhưng trả sai cho dữ liệu blank/null | Compiler không kiểm tra business semantics | Viết tests với expected theo hợp đồng. |
| Nhánh fallback che subtype mới | `default` làm switch vẫn exhaustive khi hệ kiểu mở rộng | Trên sealed hierarchy, cân nhắc bỏ default để compiler nhắc cập nhật. |
| Build cảnh báo nhưng CI vẫn xanh | Warning chưa được coi là error | Đánh giá chính sách `-Xlint`, `-Werror` thay vì suy đoán có lỗi. |

Khi gặp một diagnostic, hãy **sửa nguyên nhân gần nhất và biên dịch lại**. Một lỗi cú pháp ở đầu file có thể kéo theo nhiều lỗi thứ cấp. Không nên “chữa” bằng cách thêm cast, thêm default hoặc tắt warning mà không hiểu nghĩa của lỗi gốc.

## 14. Bài tập tự đánh giá

### Bài A — Hoàn thiện switch exhaustive

Cho:

```java
sealed interface Event permits Created, Deleted {}
record Created(String id) implements Event {}
record Deleted(String id) implements Event {}

// KHÔNG BIÊN DỊCH: thiếu Deleted.
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "created:" + id;
    };
}
```

**Yêu cầu:** Sửa không dùng `default`, thêm hành vi null rõ ràng.

**Đáp án:**

```java
static String describe(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created(var id) -> "created:" + id;
        case Deleted(var id) -> "deleted:" + id;
    };
}
```

Compiler kiểm tra đủ subtype. Test `Created("A")`, `Deleted("B")` và null để kiểm chứng nội dung nhánh.

### Bài B — Phát hiện case bị dominated

```java
// KHÔNG BIÊN DỊCH.
static String classify(Object input) {
    return switch (input) {
        case Number n -> "number";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Sửa bằng cách chuyển `case Integer n` trước `case Number n`. Lý do: mọi Integer đều là Number. Sau sửa, test `7` trả `integer`, `7L` trả `number`, và chuỗi trả `other`. Nếu chỉ thêm `default`, bạn chưa xử lý domination.

### Bài C — Guard false cũng phải có nhánh

Cho:

```java
record Order(int quantity) {}

// KHÔNG BIÊN DỊCH khi selector có kiểu Order và chỉ có guarded case.
static String status(Order order) {
    return switch (order) {
        case Order(var quantity) when quantity > 0 -> "ok";
    };
}
```

Bổ sung:

```java
static String status(Order order) {
    return switch (order) {
        case null -> "missing";
        case Order(var quantity) when quantity > 0 -> "ok";
        case Order(var quantity) -> "invalid";
    };
}
```

Test `Order(1)` → `ok`; `Order(0)` và `Order(-1)` → `invalid`; null → `missing`. Compiler bảo đảm pattern đủ nhánh, còn test xác nhận định nghĩa “số lượng dương” đúng theo nghiệp vụ.

### Bài D — Tương thích Java 17

Cho:

```java
record Pair(String left, String right) {}

// KHÔNG BIÊN DỊCH với source level 17:
static String left(Object input) {
    if (input instanceof Pair(var a, var b)) return a;
    return "other";
}
```

Viết lại để tương thích Java 17:

```java
static String left(Object input) {
    if (input instanceof Pair pair) {
        return pair.left();
    }
    return "other";
}
```

Test `new Pair("A","B")` → `A` và null → `other`. Bài tập này không yêu cầu nâng release; mục tiêu là hiểu ranh giới giữa **record class** (Java 16+) và **record deconstruction pattern** (Java 21 final).

## 15. Checklist chốt trước khi nộp code Pattern Matching

1. **Đúng JDK?** Xem `java -version`, `javac -version`, Maven/Gradle toolchain, CI image.
2. **Đúng source/release?** Type pattern `instanceof` hoạt động từ Java 16; record/switch pattern chuẩn từ Java 21.
3. **Có lạm dụng preview?** Không bật preview cho tính năng đã chính thức hoặc để “ép” cú pháp tương lai về release cũ.
4. **Flow scope hợp lệ?** Biến pattern chỉ dùng ở đường control flow mà compiler bảo đảm đã khớp.
5. **Case pattern đủ component?** Kiểm tra arity và kiểu tương ứng với khai báo record.
6. **Switch exhaustive?** Đặc biệt quan tâm sealed hierarchy, guard `when` và fallback có chủ đích.
7. **Case order hợp lệ?** Case hẹp trước case rộng; guard cụ thể trước case không guard cùng kiểu.
8. **Null được xử lý?** Phân biệt null selector với null component nằm bên trong record.
9. **Không dùng generic type argument không reifiable trong instanceof?** Dùng wildcard và kiểm tra phần tử khi cần.
10. **Compile sạch với release target?** Không chỉ dựa vào IDE tô màu hoặc một class cũ còn trên đĩa.
11. **Tests có expected độc lập?** Kiểm tra match, non-match, guard true/false, giá trị biên và ngoại lệ.
12. **CI chạy cả compile và test?** Compiler giúp phát hiện nhiều lỗi cấu trúc; test bảo vệ ngữ nghĩa.
13. **Negative compilation tests được tách riêng?** Không đặt code cố ý sai vào source build thường.
14. **Đã xem lại lỗi sau sửa?** Không dùng `default` hoặc bỏ logic để che diagnostic mà chưa hiểu nguyên nhân.

## 16. Kết luận

**Kiểm tra với Java compiler** là bước chủ động để xác nhận một đoạn Pattern Matching **hợp lệ với phiên bản Java và hệ kiểu đã chọn**. `javac` có thể phát hiện sai scope, sai số component, thiếu case của switch expression, guard chưa bao phủ subtype, case bị dominated và nhiều lỗi generic không thể kiểm tra an toàn.

Nhưng **compile success không thay thế runtime tests**. Chương trình Java 21 ở mục 9 cho thấy sự kết hợp đúng: compiler chấp nhận sealed switch và record patterns; **16 assertions** xác nhận đầu vào hợp lệ, blank, null, sai điều kiện và kiểu fallback cho ra đúng kết quả cụ thể.

Quy trình nên nhớ: **xác định JDK/source level → biên dịch → đọc diagnostic → sửa đúng nguyên nhân → biên dịch lại → chạy assertions → đưa vào CI**. Làm được chu trình đó, bạn không chỉ biết cú pháp mới mà còn có khả năng kiểm tra và bảo trì mã Java Pattern Matching một cách đáng tin.

**Tài liệu chính thức:**

- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 Language Specification — switch blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [javac command reference, Java 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
