# Kiểm thử type pattern match và không match trong Java

## 1. Mục tiêu: kiểm thử cả hai kết quả của một type pattern

Khi dùng pattern matching cho `instanceof`, một biểu thức như `value instanceof String text` vừa hỏi **giá trị có thuộc kiểu `String` hay không** vừa khai báo biến `text` nếu phép kiểm tra thành công. Vì vậy, khi kiểm thử, ta không chỉ cần chứng minh rằng một đối tượng `String` đi vào nhánh đúng; phải xác nhận điều gì xảy ra nếu đối tượng **không khớp**.

Các mục tiêu của bài:

- Phân biệt *type pattern match* (khớp) và *non-match* (không khớp), bao gồm `null`, kiểu khác, subtype và interface.
- Thiết kế **positive tests**, **negative tests** và **boundary tests** có expected result cụ thể.
- Kiểm tra luồng sau `instanceof`, bao gồm biến pattern, `&&`, `!` và **flow scoping**.
- Kiểm thử chuỗi điều kiện khi một đầu vào có thể khớp nhiều kiểu, chẳng hạn `String`, `Integer` hoặc `CharSequence`.
- Biết cách test cấu trúc generic qua `List<?>` và kiểm tra từng phần tử thay vì kỳ vọng generic type argument được kiểm tra tại runtime.
- Tự chạy chương trình Java với **23 assertions**, rồi áp dụng cách tổ chức tương tự vào JUnit 5.

**Phiên bản:** Type pattern với `instanceof` được chuẩn hóa từ **Java 16** theo [JEP 394](https://openjdk.org/jeps/394). Chương trình chính trong bài chạy với **JDK 17+** và không cần preview. Phần mở rộng về type patterns trong `switch` áp dụng **Java 21+** (JEP 441).

## 2. Match và non-match thực sự có nghĩa gì?

Xét một phương thức nhận `Object`:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "text:" + text;
    }
    return "not-a-string";
}
```

Khi `value` là một đối tượng `String` không null, type pattern **khớp**. Java có thể sử dụng `text` dưới kiểu `String` trong thân `if` mà không cần viết `(String) value`.

Khi `value` là `Integer`, `StringBuilder`, `null` hoặc kiểu khác không tương thích với `String`, type pattern **không khớp**. Thân `if` bị bỏ qua và phương thức trả `not-a-string`.

Có một số điểm dễ nhầm:

1. **Không phải so sánh tên class.** `instanceof Interface i` còn có thể khớp các implementation của interface, kể cả khi tên class runtime khác tên interface.
2. **Không yêu cầu chính xác cùng một class.** Khi pattern kiểm tra một superclass hoặc interface, các đối tượng của subtype tương thích vẫn có thể khớp.
3. **`null` không khớp type pattern trong `instanceof`.** Phép kiểm tra trả `false`; tự nó không ném `NullPointerException`.
4. **Không khớp không mặc định là lỗi.** Việc trả fallback, ném ngoại lệ hay thử pattern khác là quyết định của code bao quanh, phải được kiểm thử.
5. **Biến pattern chỉ được dùng ở nơi pattern chắc chắn đã khớp.** Nhánh non-match không có biến `text` hợp lệ để truy cập.

Với biến kiểu `Object`:

```java
Object a = "hello";
Object b = 7;
Object c = null;

System.out.println(a instanceof String text); // true
System.out.println(b instanceof String text); // false
System.out.println(c instanceof String text); // false
```

Đoạn mã trên là snippet minh họa ba phép kiểm tra riêng. Trong mã thực tế, ta thường dùng biến được ràng buộc ngay trong thân `if` để tránh cảnh báo biến không sử dụng và chứng minh nhánh đã khớp thực sự xử lý đúng dữ liệu.

## 3. Thiết kế ma trận kiểm thử: đừng chỉ đưa một String hợp lệ

Giả sử phương thức sẽ phân loại đầu vào theo thứ tự:

```java
static String classify(Object input) {
    if (input instanceof String text) {
        if (text.isBlank()) return "blank-text";
        return "text:" + text.strip();
    }
    if (input instanceof Integer number) {
        return number >= 0 ? "nonnegative:" + number : "negative:" + number;
    }
    return input == null ? "null" : "unsupported:"
            + input.getClass().getSimpleName();
}
```

Ma trận kiểm thử nên bao phủ **từng kiểu khớp, từng kiểu không khớp và các điều kiện bên trong nhánh**:

| Đầu vào `input` | Pattern `String` | Pattern `Integer` | Kết quả mong đợi |
| --- | --- | --- | --- |
| `" Java "` | Match | Không xét vì đã `return` | `text:Java` |
| `""` | Match | Không xét | `blank-text` |
| `"   "` | Match | Không xét | `blank-text` |
| `0` | Non-match | Match | `nonnegative:0` |
| `7` | Non-match | Match | `nonnegative:7` |
| `-3` | Non-match | Match | `negative:-3` |
| `3.5` | Non-match | Non-match | `unsupported:Double` |
| `true` | Non-match | Non-match | `unsupported:Boolean` |
| `new StringBuilder("ab")` | Non-match | Non-match | `unsupported:StringBuilder` |
| `null` | Non-match | Non-match | `null` |

**Vì sao cần từng nhóm?**

- Chỉ test `"Java"` chưa chứng minh code xử lý chuỗi rỗng/trắng đúng.
- Chỉ test `7` chưa chứng minh điều kiện `number >= 0` xử lý `0` hoặc số âm đúng.
- Chỉ test một đối tượng `Integer` chưa chứng minh giá trị `Double` không bị đưa nhầm vào nhánh Integer.
- Chỉ test các kiểu được hỗ trợ chưa chứng minh nhánh fallback hoặc xử lý `null` hoạt động.
- Một test dùng `new StringBuilder("ab")` giúp phân biệt `String` với lớp **cũng chứa ký tự nhưng không phải String**.

Điểm quan trọng: thay vì chỉ viết `assertFalse(input instanceof String)`, hãy **gọi phương thức đang được kiểm thử** và xác nhận kết quả dự kiến của luồng non-match.

## 4. Kiểu cha, interface và subtype: chọn dữ liệu đúng

Type pattern dựa trên khả năng tương thích kiểu runtime. Do đó nên kiểm thử cả **match nhờ interface**, chứ không chỉ match chính xác tên class.

```java
static String textLength(Object input) {
    if (!(input instanceof CharSequence sequence)) {
        return "not-textual";
    }
    return "length:" + sequence.length();
}
```

Với ví dụ này:

- `"Java"` khớp `CharSequence` vì `String implements CharSequence` → `length:4`.
- `new StringBuilder("abc")` cũng khớp `CharSequence` → `length:3`.
- `new Object()` không khớp → `not-textual`.
- `null` không khớp → `not-textual`.

Một cách viết test sai là giả định chỉ `String` mới khớp `CharSequence`. Cách đúng là dựa vào hệ kiểu, không đoán từ tên kiểu cụ thể của object.

**Chú ý về static type:** Không phải mọi biểu thức `instanceof Pattern` đều hợp lệ về mặt cú pháp khi compiler đã biết kiểu tĩnh quá cụ thể. Chẳng hạn, kiểm tra `String s; if (s instanceof String text)` là kiểu kiểm tra dư thừa có thể bị Java từ chối vì biểu thức đã là subtype của kiểu pattern. Dùng đầu vào `Object` hoặc interface/supertype phù hợp trong ví dụ nếu thật sự cần kiểm tra kiểu runtime.

Đừng dùng `getClass() == String.class` thay `instanceof` nếu hợp đồng yêu cầu chấp nhận subtype/implementation. Hai cách kiểm tra đó khác nhau.

## 5. Guard và giá trị biên: match kiểu chưa đủ để thành công

Một type pattern có thể khớp trong khi **điều kiện nghiệp vụ** sau đó không thỏa. Ví dụ:

```java
static String longText(Object input) {
    if (input instanceof String text && text.length() >= 3) {
        return "long:" + text;
    }
    return "short-or-not-string";
}
```

Các ca tối thiểu:

- `"abc"`: type pattern khớp, guard đúng tại ranh giới độ dài 3 → `long:abc`.
- `"ab"`: type pattern khớp nhưng guard sai → `short-or-not-string`.
- `123`: type pattern không khớp; `text.length()` không được đánh giá vì `&&` short-circuit → `short-or-not-string`.
- `null`: type pattern không khớp, không gọi `length()` → `short-or-not-string`.

Như vậy cần phân biệt ba trạng thái kiểm thử: **pattern match + guard true**, **pattern match + guard false**, **pattern non-match**. Nếu tất cả cùng trả chung một fallback, test có thể bổ sung một helper đo số lần gọi điều kiện để kiểm tra flow khi nghiệp vụ đòi hỏi; nhưng thông thường test **kết quả công khai** và các tác dụng phụ có chủ đích là đủ.

Không được đổi biểu thức thành:

```java
// KHÔNG BIÊN DỊCH: biến text không chắc tồn tại khi pattern sai.
if (input instanceof String text || text.length() >= 3) {
    System.out.println(text);
}
```

Với `||`, khi toán hạng trái false, không có biến `text` được ràng buộc để dùng ở toán hạng phải. Với `&&`, khi toán hạng trái true, pattern đã khớp, nên vế phải có thể dùng `text`. Đây là ví dụ **flow scoping** cần hiểu để viết cả code lẫn test đúng.

## 6. Chương trình Java 17 hoàn chỉnh: 23 phép kiểm thử có assertion

Tạo file **`TypePatternMatchTestDemo.java`** với nội dung sau:

```java
public class TypePatternMatchTestDemo {
    static String classify(Object input) {
        if (input instanceof String text) {
            if (text.isBlank()) return "blank-text";
            return "text:" + text.strip();
        }
        if (input instanceof Integer number) {
            return number >= 0 ? "nonnegative:" + number : "negative:" + number;
        }
        return input == null ? "null" : "unsupported:" + input.getClass().getSimpleName();
    }

    static String textLength(Object input) {
        if (!(input instanceof CharSequence sequence)) return "not-textual";
        return "length:" + sequence.length();
    }

    static String longText(Object input) {
        if (input instanceof String text && text.length() >= 3) {
            return "long:" + text;
        }
        return "short-or-not-string";
    }

    static String countNonblankStrings(Object input) {
        if (!(input instanceof java.util.List<?> items)) return "not-a-list";
        int count = 0;
        for (Object element : items) {
            if (element instanceof String text && !text.isBlank()) {
                count++;
            }
        }
        return "nonblank-strings:" + count;
    }

    static int checked;
    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected + " actual=" + actual);
        }
        checked++;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        expect("string", "text:Java", classify(" Java "));
        expect("empty-string", "blank-text", classify(""));
        expect("whitespace-string", "blank-text", classify("   "));
        expect("int-zero", "nonnegative:0", classify(0));
        expect("int-positive", "nonnegative:7", classify(7));
        expect("int-negative", "negative:-3", classify(-3));
        expect("double-not-integer", "unsupported:Double", classify(3.5));
        expect("boolean-unsupported", "unsupported:Boolean", classify(true));
        expect("null", "null", classify(null));
        expect("string-builder-no-string", "unsupported:StringBuilder", classify(new StringBuilder("ab")));
        expect("charsequence-string", "length:4", textLength("Java"));
        expect("charsequence-builder", "length:3", textLength(new StringBuilder("abc")));
        expect("charsequence-object", "not-textual", textLength(new Object()));
        expect("charsequence-null", "not-textual", textLength(null));
        expect("long-boundary-below", "short-or-not-string", longText("ab"));
        expect("long-boundary", "long:abc", longText("abc"));
        expect("long-guard-false", "short-or-not-string", longText(123));
        expect("long-null", "short-or-not-string", longText(null));
        expect("list-match", "nonblank-strings:2", countNonblankStrings(java.util.Arrays.asList("a", "", 7, null, "xy")));
        expect("list-empty", "nonblank-strings:0", countNonblankStrings(java.util.List.of()));
        expect("list-mixed", "nonblank-strings:0", countNonblankStrings(java.util.Arrays.asList(1, 2, null)));
        expect("list-nonmatch", "not-a-list", countNonblankStrings("a"));
        expect("list-null", "not-a-list", countNonblankStrings(null));
        System.out.println("checks=" + checked);
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 TypePatternMatchTestDemo.java
java TypePatternMatchTestDemo
```

**Đầu ra chính xác:**

```text
PASS string => text:Java
PASS empty-string => blank-text
PASS whitespace-string => blank-text
PASS int-zero => nonnegative:0
PASS int-positive => nonnegative:7
PASS int-negative => negative:-3
PASS double-not-integer => unsupported:Double
PASS boolean-unsupported => unsupported:Boolean
PASS null => null
PASS string-builder-no-string => unsupported:StringBuilder
PASS charsequence-string => length:4
PASS charsequence-builder => length:3
PASS charsequence-object => not-textual
PASS charsequence-null => not-textual
PASS long-boundary-below => short-or-not-string
PASS long-boundary => long:abc
PASS long-guard-false => short-or-not-string
PASS long-null => short-or-not-string
PASS list-match => nonblank-strings:2
PASS list-empty => nonblank-strings:0
PASS list-mixed => nonblank-strings:0
PASS list-nonmatch => not-a-list
PASS list-null => not-a-list
checks=23
```

**Những gì test thực sự chứng minh trong phạm vi ví dụ:**

- Ba ca `String` khớp pattern nhưng phân nhánh thành chuỗi có nội dung và chuỗi trắng/rỗng.
- Ba ca `Integer` khớp sau khi pattern `String` không khớp, đồng thời kiểm tra ranh giới 0.
- `Double`, `Boolean` và `StringBuilder` không khớp hai pattern `String`/`Integer`, đi đúng nhánh fallback.
- `null` không khớp type pattern và được xử lý riêng mà không dereference.
- Hai triển khai khác nhau của `CharSequence` đều khớp interface pattern; `Object` và `null` không khớp.
- Các ca `longText` phân biệt nhánh match + guard true, match + guard false, non-match và null.
- `List<?>` kiểm tra **kiểu container**; vòng lặp kiểm tra **kiểu từng phần tử**. Dữ liệu trộn `String`, số và null phải cho ra số lượng String không trắng chính xác.

Helper `expect` ném `AssertionError` nếu actual khác expected, nên chương trình **thất bại ngay** khi một giả định trong test sai. In `PASS` chỉ xảy ra sau khi so sánh bằng nhau. Dòng `checks=23` xác nhận 23 assertions của bản demo đã vượt qua, **không có nghĩa toàn bộ trạng thái và đầu vào có thể có của mọi ứng dụng đã được kiểm thử**.

## 7. Viết lại thành JUnit 5 khi dùng trong dự án

Trong một dự án Maven hoặc Gradle có dependency **JUnit Jupiter**, nên tách production code khỏi test code và dùng `@Test`/`assertEquals` để test runner phát hiện lỗi, đếm test và báo cáo.

Ví dụ file test **`TypePatternMatchJUnitTest.java`** đặt trong cùng package với class `TypePatternMatchTestDemo`:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class TypePatternMatchJUnitTest {
    @Test
    void stringMatchAndNonMatch() {
        assertAll(
            () -> assertEquals("text:Java",
                    TypePatternMatchTestDemo.classify(" Java ")),
            () -> assertEquals("blank-text",
                    TypePatternMatchTestDemo.classify("  ")),
            () -> assertEquals("unsupported:Double",
                    TypePatternMatchTestDemo.classify(3.5)),
            () -> assertEquals("null",
                    TypePatternMatchTestDemo.classify(null))
        );
    }

    @Test
    void interfacePatternAndGuardBoundary() {
        assertEquals("length:3",
                TypePatternMatchTestDemo.textLength(new StringBuilder("abc")));
        assertEquals("not-textual",
                TypePatternMatchTestDemo.textLength(new Object()));
        assertEquals("long:abc",
                TypePatternMatchTestDemo.longText("abc"));
        assertEquals("short-or-not-string",
                TypePatternMatchTestDemo.longText("ab"));
    }

    @Test
    void listContainerAndElementPatterns() {
        assertEquals("nonblank-strings:2",
                TypePatternMatchTestDemo.countNonblankStrings(
                        java.util.Arrays.asList("a", "", 7, null, "xy")));
        assertEquals("not-a-list",
                TypePatternMatchTestDemo.countNonblankStrings("not a list"));
    }
}
```

Đây là **mẫu JUnit**, cần JUnit 5 có sẵn trên test classpath; riêng đoạn test không chạy độc lập bằng hai lệnh `javac/java` ở mục 6 nếu thiếu dependency. Với một dự án sử dụng Maven/Gradle, hãy chạy qua cấu hình test runner thực tế. Phần test dùng các phương thức `static` package-private của lớp demo trong cùng package để không cần thay đổi code sản phẩm.

Gợi ý tổ chức test:

1. Đặt tên test diễn tả **cả điều kiện và kết quả**: `whenDouble_thenFallback` hoặc `whenNull_thenDefault`.
2. Mỗi test tập trung một nhóm hành vi có ý nghĩa; test parameterized có thể phù hợp với ma trận hàng chục đầu vào.
3. Bảo đảm test non-match không vô tình lặp lại cùng một nhánh fallback nhưng bỏ qua null và subtype.
4. Khi nghiệp vụ yêu cầu fail fast, bổ sung `assertThrows` để xác nhận loại ngoại lệ và thông báo mong đợi.
5. Theo dõi coverage để tìm nhánh chưa chạy, nhưng không dùng coverage thay cho việc xác định expected result.

## 8. Kiểm thử generic type pattern: khác biệt giữa container và phần tử

Một lỗi phổ biến là nghĩ rằng kiểm tra:

```java
// KHÔNG BIÊN DỊCH nếu raw là Object:
if (raw instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

sẽ xác minh được phần tử `String`. Trong Java, type argument của phần lớn generic type bị **type erasure** nên `List<String>` không phải type pattern reifiable phù hợp trong tình huống `Object raw`. Hãy kiểm tra container bằng `List<?>`, rồi xác nhận kiểu từng phần tử:

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

Đây là snippet có thể đặt trong class phù hợp và biên dịch với Java 17+. Cần phân biệt:

- **Container match:** `new ArrayList<Integer>()` vẫn khớp `List<?>`.
- **Element match:** phần tử `Integer` không khớp `String text`, còn phần tử `String` thì khớp.
- **Null element:** `null instanceof String text` là false, không phát sinh lỗi chỉ vì phép `instanceof`.
- **Empty list:** container match nhưng số lượng phần tử hợp lệ bằng 0.
- **Non-list input:** container không match và hàm trả giá trị fallback.

Nếu test chỉ dùng `List<String>`, bạn không phát hiện lỗi khi runtime nhận list hỗn hợp từ dữ liệu legacy. Ví dụ đầy đủ ở mục 6 đã đưa `List<?>`, dữ liệu trộn và null vào cùng ma trận.

## 9. Phạm vi biến pattern: có trường hợp sai ngay khi biên dịch

Có những lỗi không thể kiểm thử bằng runtime vì compiler không chấp nhận mã. Chẳng hạn:

```java
// KHÔNG BIÊN DỊCH: text không chắc tồn tại sau if.
static int wrongScope(Object raw) {
    if (raw instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

Sau `if`, raw có thể không phải `String`; `text` không được bảo đảm ràng buộc. Sửa bằng guard clause phủ định:

```java
static int safeLength(Object raw) {
    if (!(raw instanceof String text)) return -1;
    return text.length();
}
```

Với bản đúng, tập kiểm thử tối thiểu nên gồm:
- `safeLength("hi") == 2`: pattern match, biến pattern được dùng.
- `safeLength(10) == -1`: không match, thoát sớm.
- `safeLength(null) == -1`: null cũng không match.

**Phân biệt:** compiler bảo đảm biến pattern không bị dùng trên đường không khớp, nhưng compiler **không chứng minh business rule đã đúng**. Nếu độ dài phải lớn hơn 0, bạn vẫn phải thêm điều kiện và test riêng.

Nếu đang review code, hãy xem một lỗi compiler do scope hoặc do type pattern không hợp lệ là **lỗi ở mức cú pháp/kiểu**, không phải một nhánh runtime mà test cần tìm cách kích hoạt.

## 10. Mở rộng: kiểm thử type patterns trong switch (Java 21+)

Từ Java 21, type patterns cũng có thể xuất hiện trong các nhánh `case` của `switch`:

```java
// Java 21+, snippet đặt trong phương thức nhận Object input.
String label = switch (input) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    case Integer n -> "integer:" + n;
    default -> "unsupported";
};
```

Ma trận kiểm thử tương ứng:

| Input | Nhánh phải khớp | Kết quả |
| --- | --- | --- |
| `" "` | `case String s when s.isBlank()` | `blank` |
| `"Java"` | `case String s` | `text:Java` |
| `7` | `case Integer n` | `integer:7` |
| `3.5` | `default` | `unsupported` |
| `null` | `case null` | `missing` |

Điểm khác biệt với `instanceof`:

- `case String s` không guard nếu đặt **trước** `case String s when ...` sẽ che nhánh có guard. Compiler có thể báo *dominated case label*.
- `switch expression` trên kiểu mở như `Object` cần nhánh bao quát như `default` để xử lý hết các kiểu khác.
- `case null` xử lý selector null. **`default` không nên được coi là thay thế cho `case null`**.
- Khi có guard `when`, test phải chạy được cả **guard true** và **guard false**. Một test chỉ xác nhận input là `String` chưa đủ.

Đoạn Java 21 ở mục này là snippet hướng dẫn mở rộng; chương trình chạy độc lập ở mục 6 cố ý chỉ dùng các tính năng ổn định của Java 17.

## 11. Tránh những kiểu test dễ tạo cảm giác an toàn giả

| Cách test chưa tốt | Vấn đề | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ dùng một `String` hợp lệ | Không có bằng chứng non-match, null hoặc guard false. | Lập ma trận nhiều kiểu, null và giá trị biên. |
| Chỉ gọi `System.out.println(actual)` | Code có thể in sai mà test vẫn được coi là “chạy xong”. | Dùng `assertEquals`/`AssertionError` với expected cụ thể. |
| Test `obj instanceof String` mà không gọi hàm sản phẩm | Chưa chứng minh hàm xử lý nhánh non-match đúng. | Test kết quả/ngoại lệ của chính hàm cần kiểm tra. |
| Nghĩ `StringBuilder` khớp `String` | Nhầm lớp chứa ký tự với subtype của String. | Test `StringBuilder` là non-match của `String` và match của `CharSequence`. |
| Bỏ test null | Null không match mọi type pattern trong `instanceof`. | Xác nhận đường fallback hoặc exception cho null theo hợp đồng. |
| Không test interface/subtype | Có thể viết nhầm exact class check thay cho `instanceof`. | Dùng các implementation khác nhau của cùng interface. |
| Không test `&&` guard false | Pattern có thể match nhưng điều kiện bổ sung vẫn false. | Test tại ngưỡng, dưới ngưỡng và sai kiểu. |
| Kiểm tra `List<String>` như kiểu runtime | Generic element type không được đảm bảo qua erasure. | Dùng `List<?>` rồi match từng element. |
| Test nhánh fallback với mỗi một kiểu khác | Không phát hiện sự khác biệt giữa sai kiểu và null. | Tách ca null, kiểu khác, container và element. |
| Chỉ quan sát branch coverage 100% | Không khẳng định giá trị biên hay expected business result. | Kết hợp coverage với assertions và data partitions. |
| `catch (Exception e) {}` trong negative test | Có thể che exception sai loại, làm test pass giả. | Dùng `assertThrows` hoặc helper kiểm tra đúng exception. |
| Chỉ test `case String s` trong switch | Có thể bỏ sót `when`, `case null` và `default`. | Test từng nhánh và điều kiện điều hướng. |

### Dữ liệu test phải kích hoạt đúng nhánh

Đặc biệt với một chuỗi `if / else if`, nếu nhánh đầu match và `return`, nhánh sau không bao giờ được xét. Muốn kiểm thử nhánh `Integer` của `classify`, đầu vào phải **không khớp String** và **khớp Integer**. Muốn kiểm thử fallback, đầu vào phải **không khớp cả String lẫn Integer**.

Không nên đánh dấu test non-match là PASS chỉ vì phương thức trả bất kỳ giá trị khác null; cần so sánh đúng kết quả nghiệp vụ. Nếu code ném ngoại lệ khi input không phù hợp, negative test cần chứng minh nó ném đúng exception thay vì nhận fallback thành công.

## 12. Bài tập thực hành: tự thiết kế test cho type pattern

Cho phương thức:

```java
static String formatCode(Object value) {
    if (value instanceof String code && code.length() == 4) {
        return "code:" + code;
    }
    if (value instanceof Number number) {
        return "number:" + number.intValue();
    }
    return value == null ? "missing" : "invalid";
}
```

**Câu hỏi:** Hãy lập bộ test kiểm tra pattern String match/non-match, guard true/false, pattern Number match, kiểu ngoài hỗ trợ và null. Đặc biệt, liệu `Integer`, `Long` và `Double` có cùng khớp pattern `Number number` không?

**Đáp án và ca kiểm thử gợi ý:**

1. `formatCode("AB12")` → `code:AB12`: String match, độ dài đúng 4.
2. `formatCode("ABC")` → `invalid`: String match nhưng guard false; Number non-match.
3. `formatCode("")` → `invalid`: String match nhưng không đủ độ dài.
4. `formatCode(7)` → `number:7`: Integer là subtype của Number.
5. `formatCode(7L)` → `number:7`: Long cũng khớp Number.
6. `formatCode(3.9)` → `number:3`: Double khớp Number và `intValue()` chuyển giá trị theo quy tắc số của Java; ở đây lấy phần nguyên 3.
7. `formatCode(true)` → `invalid`: Boolean không phải Number và không phải String.
8. `formatCode(null)` → `missing`: cả hai pattern đều không khớp.
9. `formatCode(new StringBuilder("AB12"))` → `invalid`: không phải String cũng không phải Number.

Những ca trên vừa kiểm tra **nhánh được chọn** vừa xác nhận **kiểu mở rộng** `Number` chấp nhận các subclass. Điều này giúp phát hiện sai lầm nếu ai đó refactor thành `value instanceof Integer` mà quên Long/Double. Nếu muốn tránh mất độ chính xác khi chuyển Double thành int, yêu cầu nghiệp vụ và mã cần thay đổi; test hiện tại phản ánh đúng hành vi đã viết chứ không tự suy luận ý nghĩa tài chính.

Các đoạn trong bài tập là snippet đặt trong một class thích hợp; chương trình độc lập có `main`, các assertions và đầu ra được xác nhận nằm ở mục 6.

## 13. Checklist áp dụng vào dự án

Trước khi coi việc kiểm thử type pattern đã đủ:

1. **Ghi rõ pattern và nhánh cần test**: `String`, `Integer`, `CharSequence`, `Number`, `List<?>` hoặc loại dữ liệu thực tế của ứng dụng.
2. **Ít nhất một positive test** cho mỗi nhánh match cần thiết, với giá trị có thể xác nhận được.
3. **Ít nhất một negative test** để kích hoạt đường không match; nếu có nhiều loại dữ liệu sai khác nhau, chọn các nhóm mang ý nghĩa.
4. **Test null riêng** vì null không khớp `instanceof` và có thể được xử lý khác các kiểu sai.
5. **Test subtype/interface** khi pattern dùng superclass hoặc interface.
6. **Test guard true/false và giá trị biên** khi nhánh match có kiểm tra thêm, ví dụ `length >= 3` hoặc `number >= 0`.
7. **Test fallback/exception** đúng theo hợp đồng, không chỉ kiểm tra “phương thức không crash”.
8. **Dùng assertions tự động** và xem báo cáo lỗi; có thể chuyển ma trận sang JUnit parameterized tests nếu nhiều bộ dữ liệu.
9. **Lưu ý type erasure**: kiểm tra `List<?>` không chứng minh mọi phần tử có kiểu `String`.
10. **Không nhầm compile-time errors với runtime non-match**: lỗi scope hoặc pattern không hợp lệ phải sửa code, còn non-match hợp lệ cần test hành vi runtime.

**Ghi nhớ:** Kiểm thử type pattern đúng phải chứng minh **khi khớp thì biến được dùng và kết quả chính xác; khi không khớp thì chương trình chuyển sang đúng nhánh, đúng kết quả hoặc đúng ngoại lệ**. Hãy kiểm thử `null`, kiểu ngoài dự kiến, interface/subtype và giá trị biên của guard, thay vì chỉ viết một happy-path assertion.

**Tài liệu tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html), [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441), [Java SE 17 Language Specification — instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
