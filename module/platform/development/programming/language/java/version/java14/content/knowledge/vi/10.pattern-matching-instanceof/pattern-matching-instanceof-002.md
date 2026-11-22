# Từ preview Java 14 tới type pattern `instanceof` chính thức từ Java 16

> **Module:** Java 14 — **Mẫu `instanceof`**. Pattern matching cho `instanceof` được giới thiệu ở Java 14 dưới dạng **preview** (JEP 305), được thử nghiệm thêm ở Java 15 (JEP 375), rồi trở thành **tính năng chính thức ở Java 16 (JEP 394)**. Bài này chỉ dạy cú pháp và ngữ nghĩa **đã chính thức, còn áp dụng tới Java hiện đại**. Hãy dùng một JDK còn được cập nhật như JDK 21 hoặc 25; các ví dụ dùng `javac --release 17` và **không cần JDK 14 cũ hay `--enable-preview`**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu vì sao `instanceof` truyền thống thường đi kèm ép kiểu, còn **type pattern** cho phép vừa kiểm tra vừa tạo biến đã được xác định kiểu.
2. Giải thích đúng lịch sử **preview Java 14 → preview Java 15 → chính thức Java 16**, mà không tiếp tục sử dụng quy trình/cờ preview của tài liệu cũ.
3. Dùng `if (value instanceof String text)` để xử lý đúng kiểu runtime mà không cần cast thủ công.
4. Hiểu **flow scoping**: biến pattern chỉ được phép dùng tại nơi compiler xác định pattern đã match, kể cả trong biểu thức logic và sau guard clause.
5. Xử lý `null`, kiểu không khớp, interface/superclass và dữ liệu generic một cách an toàn.
6. Nhận diện lỗi compile-time vì kiểm tra kiểu dư thừa, sử dụng biến sai phạm vi hoặc dùng mẫu generic không kiểm tra được.
7. Phân biệt **type pattern `instanceof`** (Java 16) với **record pattern** và **pattern trong `switch`** (chính thức ở Java 21).
8. Chạy được ví dụ độc lập trên một Java toolchain đang được hỗ trợ.

## 2. Mốc chuẩn hóa: đâu là kiến thức còn dùng hôm nay?

| Mốc | Trạng thái | Ý nghĩa khi học hiện nay |
| --- | --- | --- |
| Java 14 — JEP 305 | **Preview lần đầu** cho pattern matching với `instanceof` | Đây là mốc nguồn gốc lịch sử, chưa phải bản chính thức ở Java 14. |
| Java 15 — JEP 375 | **Preview lần hai** | Vẫn là giai đoạn thử nghiệm, không lấy hướng dẫn preview cũ làm quy tắc sử dụng. |
| Java 16 — JEP 394 | **Chính thức** | `instanceof Type variable` trở thành cú pháp Java ổn định, không yêu cầu bật preview. |
| Java 17/21/25 và các bản mới hơn hỗ trợ ngôn ngữ tương ứng | Tiếp tục hỗ trợ cú pháp chính thức | Học và chạy trên JDK được cập nhật theo phiên bản đích của dự án. |

Ở mốc Java 16, hai điểm kỹ thuật được chốt:

- Pattern variable **không còn ngầm định `final`**. Nó hoạt động giống biến cục bộ về khả năng gán lại; viết mã rõ ràng vẫn thường có lợi hơn thay đổi giá trị của nó.
- Compiler từ chối một phép kiểm tra pattern **dư thừa khi kiểu tĩnh của biểu thức bên trái đã là subtype của kiểu đích**: ví dụ biến tĩnh kiểu `String` mà lại viết `instanceof String s`. Khi chỉ cần gọi phương thức của kiểu đã biết, hãy dùng trực tiếp biến đang có.

Hãy dùng quy tắc final của Java 16+, không dùng tùy chọn `--enable-preview` cho tính năng này. Việc module có tên **Java 14** chỉ cho biết nơi tính năng được giới thiệu, **không buộc phải cài hoặc chạy JDK 14 đã hết chu kỳ hỗ trợ thông thường**.

## 3. Cú pháp type pattern chính thức

Dạng tổng quát:

~~~java
expression instanceof ReferenceType variable
~~~

Đây là **mẫu cú pháp**, chưa phải một chương trình biên dịch độc lập.

- `expression`: giá trị cần thử kiểu, chẳng hạn tham số kiểu `Object`.
- `ReferenceType`: kiểu tham chiếu phù hợp với quy tắc Java, chẳng hạn `String`, `Number`, interface `CharSequence`, record `Point` hoặc kiểu mảng.
- `variable`: **pattern variable** chỉ được khởi tạo khi giá trị runtime match kiểu.
- Toàn bộ phép thử trả về `boolean`. Khi `true`, Java đã xác định biến `variable` có kiểu yêu cầu, nên không cần ép kiểu thủ công.

Ví dụ mảnh lệnh trong một phương thức:

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Khi `value` chứa `"Java"`, nhánh đúng chạy và `text.length()` trả về 4. `text` là `String`. Không cần `String text = (String) value;`.

Nếu giá trị là `null` hoặc không thuộc kiểu tương thích `String`, pattern không match; biến `text` không được dùng ở đường không match. Đó là **ràng buộc an toàn của trình biên dịch**, chứ không phải một cast luôn thành công.

## 4. So sánh kiểm tra kiểu thông thường và type pattern

Dạng truyền thống vẫn là Java hợp lệ:

~~~java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Dạng chính thức với type pattern, Java 16+:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Đây là hai **mảnh lệnh** có cùng mục đích. Ở dạng cũ, lập trình viên lặp lại `String` và giữ lời gọi cast đồng bộ với phép thử. Dạng type pattern thể hiện trực tiếp **kiểm tra kiểu + khai báo biến kiểu đó khi match**.

Type pattern giúp giảm nguy cơ copy/paste sai kiểu giữa `instanceof` và cast, nhưng không có nghĩa mọi phép ép kiểu trong chương trình đều biến mất. Chỉ các đường đi được compiler chứng minh match mới được phép dùng biến.

### Ví dụ 1: chương trình độc lập

Tạo tệp **`InstanceofBasicsDemo.java`**:

~~~java
public class InstanceofBasicsDemo {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "text(" + text.length() + "): " + text;
        }
        if (value instanceof Integer number) {
            return "integer x2: " + (number * 2);
        }
        if (value == null) {
            return "null";
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(21));
        System.out.println(describe(null));
        System.out.println(describe(3.5));
    }
}
~~~

Biên dịch và chạy trên JDK 21 hoặc 25 có hỗ trợ `--release 17`:

~~~bash
javac --release 17 InstanceofBasicsDemo.java
java InstanceofBasicsDemo
~~~

**Stdout chính xác:**

~~~text
text(4): Java
integer x2: 42
null
other
~~~

Giải thích: `"Java"` là `String` nên `text` được tạo; `21` được autobox thành `Integer` khi truyền vào tham số `Object`; `null` không match type pattern tham chiếu; `3.5` là `Double` nên không match `Integer`. Chú ý sự khác nhau giữa **kiểu tĩnh `Object` của tham số** và **kiểu runtime của từng giá trị**.

## 5. Flow scoping: biến pattern chỉ có mặt khi chắc chắn match

Phạm vi (*scope*) của pattern variable phụ thuộc vào **luồng điều khiển**. Với đoạn:

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Đúng
} else {
    System.out.println("not a string");
    // text không có ở nhánh này
}
~~~

Nếu giá trị không phải `String`, nhánh `else` chạy và `text` không được khởi tạo. Vì vậy không thể dùng `text` trong nhánh `else` hoặc ngay sau câu `if` nếu cả hai đường đúng/sai vẫn có thể tiếp tục tới đó.

Sơ đồ:

~~~text
value instanceof String text
            |
       +----+----+
     true       false
       |          |
 text được    text chưa
 khởi tạo     khởi tạo
       |          |
 dùng text    không dùng text
~~~

Điều này được gọi là **flow scoping** hay phạm vi theo luồng: compiler đưa biến vào scope ở vị trí mà pattern đã **definitely matched**. Cách xác định không đơn giản là “biến tồn tại trong mọi khối ngoặc sau chữ `instanceof`”.

### Ví dụ 2: nhiều kiểu, các nhánh riêng

Tạo tệp **`PatternBranchDemo.java`**:

~~~java
public class PatternBranchDemo {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "String with " + text.length() + " chars";
        } else if (value instanceof Number number) {
            return "Number: " + number.intValue();
        }
        return "Unsupported";
    }

    public static void main(String[] args) {
        System.out.println(classify("code"));
        System.out.println(classify(7.5));
        System.out.println(classify(false));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PatternBranchDemo.java
java PatternBranchDemo
~~~

**Stdout chính xác:**

~~~text
String with 4 chars
Number: 7
Unsupported
~~~

`7.5` là `Double` và `Double` mở rộng `Number`, vì vậy `number.intValue()` trả 7. Không cần cast thủ công ở cả hai nhánh.

## 6. Toán tử `&&`: dùng biến sau khi vế trái match

Với **`&&`**, Java chỉ đánh giá vế phải nếu vế trái đúng. Do đó:

~~~java
if (value instanceof String text && text.length() >= 5) {
    System.out.println(text);
}
~~~

Đây là mảnh lệnh hợp lệ: vế phải `text.length()` chỉ chạy khi `instanceof String text` đã match và `text` đã được khởi tạo.

Đối chiếu các trường hợp:

| Biểu thức | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `obj instanceof String s && s.length() > 0` | Có | Vế phải chỉ chạy khi vế trái match. |
| `s.length() > 0 && obj instanceof String s` | Không | Sử dụng `s` trước khi khai báo pattern. |
| `obj instanceof String s \|\| s.isEmpty()` | Không | `\|\|` chỉ xét vế phải khi vế trái sai, lúc đó `s` chưa được khởi tạo. |
| `obj instanceof String s && !s.isBlank() && s.length() >= 3` | Có | Các kiểm tra sau chỉ chạy khi pattern và điều kiện trước đều đúng. |

Ký hiệu trong bảng chỉ biểu thị **biểu thức**, không phải các file Java độc lập. Cần giữ `&&` và `||` khác nhau vì quy tắc *short-circuit* của chúng trái nhau.

### Ví dụ 3: điều kiện kết hợp

Tạo tệp **`PatternAndDemo.java`**:

~~~java
public class PatternAndDemo {
    static String validate(Object candidate) {
        if (candidate instanceof String text
                && !text.isBlank()
                && text.length() >= 5) {
            return "accepted: " + text;
        }
        return "rejected";
    }

    public static void main(String[] args) {
        System.out.println(validate("Java 17"));
        System.out.println(validate("Hi"));
        System.out.println(validate(null));
        System.out.println(validate(123));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PatternAndDemo.java
java PatternAndDemo
~~~

**Stdout chính xác:**

~~~text
accepted: Java 17
rejected
rejected
rejected
~~~

Với `null` và số nguyên, pattern `String text` trả false và các phép gọi `text.isBlank()`/`text.length()` không chạy. `String.isBlank()` là API Java 11, nên có sẵn ở mức target Java 17.

## 7. Phủ định và guard clause: sử dụng biến sau câu `if`

Khi đường **không match** đã bị chặn bằng `return` hoặc `throw`, các câu lệnh sau guard có thể sử dụng biến pattern:

~~~java
static int lengthOrThrow(Object candidate) {
    if (!(candidate instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text.length();
}
~~~

Đây là mảnh phương thức đặt trong một class. Nếu không phải `String` thì ném ngoại lệ, không đi tới `return`. Nếu chạy tới `return`, compiler biết `text` đã match.

### Ví dụ 4: guard clause và cập nhật biến pattern

Tạo tệp **`GuardClausePatternDemo.java`**:

~~~java
import java.util.Locale;

public class GuardClausePatternDemo {
    static String normalize(Object candidate) {
        if (!(candidate instanceof String text)) {
            return "not text";
        }

        text = text.strip();
        if (text.isEmpty()) {
            return "empty";
        }
        return text.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  "));
        System.out.println(normalize("   "));
        System.out.println(normalize(99));
        System.out.println(normalize(null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GuardClausePatternDemo.java
java GuardClausePatternDemo
~~~

**Stdout chính xác:**

~~~text
JAVA
empty
not text
not text
~~~

`text` hợp lệ sau `if` vì nhánh không match đã `return`. Phép gán `text = text.strip();` cũng hợp lệ: **pattern variable không còn ngầm định `final` kể từ Java 16**. Đây là cập nhật biến cục bộ, **không thay đổi object do caller truyền vào**.

Trong code thật, đôi khi dễ đọc hơn nếu dùng `String normalized = text.strip();` thay vì gán lại biến pattern, đặc biệt khi nhiều phép biến đổi nối tiếp.

## 8. `null`: không match type pattern tham chiếu

Với Java 16/17:

~~~java
Object input = null;
boolean matched = input instanceof String s; // false
~~~

Đây là mảnh lệnh hợp lệ; biểu thức cho kết quả `false`, không tự ném `NullPointerException`. Biến `s` không trở thành một `String` được khởi tạo để sử dụng ở đường không match.

Đừng nhầm với ép kiểu:

~~~java
String text = (String) input; // Nếu input == null thì text == null.
~~~

Việc cast `null` sang kiểu tham chiếu có thể hợp lệ, nhưng sau đó `text.length()` sẽ gây `NullPointerException` nếu không kiểm tra. Type pattern nối kiểm tra và bind, nhưng ứng dụng vẫn phải quyết định cách xử lý **dữ liệu thiếu**.

Nếu yêu cầu nghiệp vụ phân biệt `null` với kiểu không hợp lệ:

~~~java
static String describeValue(Object input) {
    if (input == null) return "missing";
    if (input instanceof String text) return "text:" + text;
    return "unexpected type";
}
~~~

Đây là mảnh phương thức; `null` được phân loại riêng.

**Không suy luận từ `switch` pattern mới hơn**: `case null` trong `switch` có ngữ nghĩa riêng ở những phiên bản Java hỗ trợ nó. Bài này bàn về **type pattern trong `instanceof`**, nơi `null` không match.

## 9. Type pattern với interface, superclass và generic

Pattern không giới hạn ở `String`. Khi cần API của một interface, có thể match trực tiếp vào interface:

~~~java
static int charCount(Object input) {
    if (input instanceof CharSequence text) {
        return text.length();
    }
    return -1;
}
~~~

Đây là mảnh phương thức. `CharSequence` có thể được triển khai bởi `String`, `StringBuilder` và các loại khác. Nếu chỉ cần `length()`, interface này diễn đạt đúng hơn việc ép tất cả về `String`.

### Ví dụ 5: interface và nhiều runtime type

Tạo tệp **`InterfacePatternDemo.java`**:

~~~java
public class InterfacePatternDemo {
    static String describe(Object input) {
        if (input instanceof CharSequence text) {
            return "chars: " + text.length();
        }
        if (input instanceof Number number) {
            return "number: " + number.intValue();
        }
        return "unsupported";
    }

    public static void main(String[] args) {
        System.out.println(describe(new StringBuilder("hello")));
        System.out.println(describe("Java"));
        System.out.println(describe(2.9));
        System.out.println(describe(true));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 InterfacePatternDemo.java
java InterfacePatternDemo
~~~

**Stdout chính xác:**

~~~text
chars: 5
chars: 4
number: 2
unsupported
~~~

Lưu ý `CharSequence` là interface, **không bảo đảm bất biến**; `StringBuilder` vẫn mutable. Một type pattern cho phép dùng API của kiểu match, không bảo đảm tính hợp lệ nghiệp vụ, an toàn dữ liệu hay tính bất biến của object.

### Generics và type erasure

Đoạn sau **không hợp lệ khi `candidate` có kiểu tĩnh `Object`**:

~~~java
if (candidate instanceof java.util.List<String> strings) {
    // Không thể kiểm tra List<String> từ Object theo cách này.
}
~~~

Đây là **mảnh code cố ý sai** để học lỗi compiler, không đưa vào file demo.

Lý do: thông tin tham số kiểu `String` của collection không được giữ đầy đủ để kiểm tra `List<String>` tại runtime. Dùng `List<?>` trước, rồi kiểm tra từng phần tử bằng type pattern:

~~~java
if (candidate instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text);
        }
    }
}
~~~

`List<?>` chỉ chứng minh đây là một `List`; nó **không** chứng minh mọi item là `String`.

### Ví dụ 6: kiểm tra collection hỗn hợp

Tạo tệp **`GenericPatternDemo.java`**:

~~~java
import java.util.List;

public class GenericPatternDemo {
    static int countNonBlankStrings(Object candidate) {
        if (!(candidate instanceof List<?> items)) {
            return -1;
        }

        int count = 0;
        for (Object item : items) {
            if (item instanceof String text && !text.isBlank()) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        System.out.println(countNonBlankStrings(
                List.of("Java", 123, "   ", "API")));
        System.out.println(countNonBlankStrings(List.of(1, 2)));
        System.out.println(countNonBlankStrings("not a list"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericPatternDemo.java
java GenericPatternDemo
~~~

**Stdout chính xác:**

~~~text
2
0
-1
~~~

`"Java"` và `"API"` là `String` không blank, trong khi `123` không match `String` và `"   "` bị loại bằng `isBlank()`. Input không phải list trả `-1` theo hợp đồng ví dụ.

## 10. Những giới hạn ở compile time cần nhớ

Java kiểm tra tính hợp lệ của pattern **trước khi chạy**. Một số lỗi điển hình:

| Trường hợp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `Object obj = "x"; obj instanceof String s` | Có | `Object` có thể mang `String` tại runtime. |
| `String s = "x"; s instanceof String text` | Không | Kiểu tĩnh `String` đã phù hợp kiểu đích; pattern type test dư thừa và bị từ chối theo JEP 394. |
| `String s = "x"; s instanceof CharSequence chars` | Không | `String` đã là subtype của `CharSequence`. |
| `obj instanceof String s && s.length() > 1` | Có nếu `obj` có kiểu phù hợp | Vế phải được xét sau khi match. |
| `obj instanceof String s \|\| s.length() > 1` | Không | Vế phải chạy khi pattern chưa match. |
| `if (!(obj instanceof String s)) return; use(s);` | Hợp lệ theo scope nếu trong phương thức `void` và `use` tồn tại | Đường không match không thể tới `use`. |
| `obj instanceof java.util.List<String> items` với `obj` kiểu `Object` | Không | `List<String>` không thể được kiểm tra đầy đủ tại runtime. |
| `obj instanceof java.util.List<?> items` với `obj` kiểu `Object` | Có | Mẫu kiểm tra kiểu tham chiếu `List<?>` phù hợp. |
| `obj instanceof int n` với `--release 17` | Không | Type pattern `instanceof` chính thức ở mốc Java 16/17 chỉ dùng kiểu tham chiếu. |
| `obj instanceof var x` với `--release 17` | Không | `var` không phải kiểu dùng trong type pattern `instanceof` đã chính thức ở Java 16. |

Các ví dụ trong bảng là **mảnh biểu thức**, bao gồm một số ví dụ sai để phân tích. Không sao chép trực tiếp biểu thức sai vào file chạy.

### Một số lỗi thực tế

- Đặt biến pattern có **tên trùng** với local variable đang nằm trong scope → báo trùng tên hoặc shadowing bị cấm.
- Dùng biến ở nhánh `else` hoặc sau `if` khi đường không match có thể tới đó → biến không được khởi tạo theo quy tắc scope.
- Dùng `||` thay cho `&&` khi kiểm tra một thuộc tính của pattern variable → vế phải không an toàn.
- Dùng một biểu thức có **kiểu tĩnh đã là subtype** của kiểu pattern → kiểm tra dư thừa, compiler từ chối.
- Tưởng `List<?>` đảm bảo phần tử có kiểu `String` → không đúng, phải kiểm tra phần tử.
- Tưởng pattern bảo đảm nội dung chuỗi hợp lệ → type pattern kiểm tra **kiểu**, validation nghiệp vụ là việc khác.

**Lỗi compile-time không có nghĩa type pattern chưa chính thức.** Chúng là các ràng buộc ngôn ngữ giúp tránh trường hợp sử dụng biến không chắc đã được khởi tạo hoặc kiểm tra kiểu không có ý nghĩa.

## 11. Phân biệt type pattern Java 16 với tính năng pattern Java 21

Pattern matching đã được mở rộng sau Java 16; các tính năng không có cùng mốc chính thức.

| Cú pháp | Chính thức từ | Ý nghĩa |
| --- | --- | --- |
| `if (obj instanceof String text)` | **Java 16** — JEP 394 | **Type pattern**: kiểm tra runtime type và bind biến `text`. |
| `if (obj instanceof Point point)` | **Java 16** nếu kiểu `Point` tồn tại và phù hợp | Type pattern dùng với một record giống dùng với class. |
| `if (obj instanceof Point(int x, int y))` | **Java 21** — JEP 440 | **Record pattern**: vừa match record vừa tách component thành biến. |
| `switch (obj) { case String s -> ... }` | **Java 21** — JEP 441 | Pattern matching trong `switch`, ngữ cảnh và quy tắc khác `instanceof`. |

Hai dòng cuối là **mảnh cú pháp minh họa tính năng Java 21**, không phải mã đưa vào một bài biên dịch `--release 17`. Chúng đều là tính năng chính thức trong Java 21+, nhưng **không thuộc phần cú pháp đã chính thức từ Java 16** đang học ở đây.

### Ví dụ 7: pattern một record như một kiểu

Tạo tệp **`RecordTypePatternDemo.java`**:

~~~java
record Point(int x, int y) {}

public class RecordTypePatternDemo {
    static String describe(Object candidate) {
        if (candidate instanceof Point point) {
            return "point: " + point.x() + "," + point.y();
        }
        return "not a point";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(3, 5)));
        System.out.println(describe("3,5"));
        System.out.println(describe(null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RecordTypePatternDemo.java
java RecordTypePatternDemo
~~~

**Stdout chính xác:**

~~~text
point: 3,5
not a point
not a point
~~~

`record` cũng trở thành tính năng chính thức ở Java 16 (JEP 395). Nhưng `candidate instanceof Point point` chỉ làm **type test và bind một biến `point`**, sau đó lấy component qua `point.x()`/`point.y()`. **Không có destructuring** như record pattern Java 21.

## 12. Khi nào nên dùng type pattern?

**Nên dùng** khi một giá trị có thể thuộc nhiều kiểu runtime và cần xử lý dựa trên kiểu cụ thể: kết quả từ API chung, collection có phần tử khác kiểu, kiểm tra một interface, hoặc guard clause trước phần xử lý chuyên biệt. Với mã cũ đang kiểm tra `instanceof` rồi cast cùng kiểu ở ngay nhánh thành công, chuyển sang pattern thường khiến ý định rõ ràng hơn.

**Cần cân nhắc thiết kế khác** khi:

- Có hàng chục nhánh `if (obj instanceof A) ...` để gọi những hành vi cùng một interface. Lúc đó **polymorphism** có thể dễ mở rộng hơn.
- API dùng `Object` quá rộng nhưng thực chất dữ liệu chỉ có một kiểu. Nên cải thiện kiểu tham số hoặc dùng generic thay vì liên tục kiểm tra runtime type.
- Logic cần kiểm tra giá trị như độ dài, nội dung mã, quyền truy cập hoặc trạng thái hợp lệ. `instanceof String s` **không xác nhận** những ràng buộc nghiệp vụ đó.
- Phải duy trì tương thích với một mức Java **thấp hơn 16**. Khi đó dùng cú pháp phù hợp mức đích của dự án và lập kế hoạch nâng cấp; không đưa Java 16 syntax vào target cũ.

Hãy chọn pattern để **diễn đạt kiểm tra và bind**, không để thay thế thiết kế hợp đồng kiểu dữ liệu.

## 13. Quy trình chuyển mã kiểm tra và ép kiểu sang pattern

1. **Xác định mức Java đích** của dự án. Type pattern `instanceof` là chính thức từ Java 16; với Java 17/21/25 sử dụng cú pháp ổn định.
2. **Tìm cặp kiểm tra và cast có cùng kiểu**: `obj instanceof Type` và `(Type) obj` trong nhánh match.
3. **Viết pattern variable** tại biểu thức `instanceof`: `obj instanceof Type item`; loại cast thủ công và cập nhật chỗ dùng.
4. **Giữ nguyên đường sai/null**: `else`, `return`, exception hoặc kết quả mặc định phải có cùng ý nghĩa nghiệp vụ.
5. **Kiểm tra flow scoping**: biến chỉ được dùng ở nơi chắc chắn match; sử dụng `&&` đúng phía, hoặc guard clause khi cần dùng sau `if`.
6. **Kiểm tra generic và mối quan hệ kiểu tĩnh**: không đưa `List<String>` vào pattern không kiểm tra được, không thực hiện pattern dư thừa.
7. **Biên dịch bằng JDK có cập nhật với `--release` phù hợp**; kiểm tra `javac --help` nếu chưa biết compiler còn hỗ trợ mức nào.
8. **Kiểm thử trường hợp match, không match, null, kiểu con** và kết quả tính toán. Chỉ hoàn thành refactor khi hành vi mong muốn được bảo toàn.

### Kiểm tra nhanh trước khi commit

| Câu hỏi | Tiêu chí |
| --- | --- |
| Có thực sự cần kiểm tra kiểu runtime không? | Nếu có, type pattern có thể hợp lý. |
| Pattern có phải cú pháp chính thức cho target không? | Target Java 16+; ví dụ lớp học chọn `--release 17`. |
| Biến có đang được dùng khi chắc chắn match? | Nhánh đúng, sau `&&` phù hợp, sau guard thoát đường sai. |
| Có nhầm `&&` với `||`? | Vế phải `||` không tự được phép dùng biến từ pattern ở vế trái. |
| Null được xử lý như thế nào? | `null` không match type pattern tham chiếu. |
| Kiểu generic có kiểm tra được không? | `List<?>` và kiểm tra từng phần tử khi cần. |
| Có vô tình dùng record/switch pattern Java 21? | Tách riêng khỏi type pattern `instanceof` Java 16. |
| Có cờ preview hoặc phụ thuộc JDK cũ? | Không cần cho type pattern đã chính thức. |

## 14. Bài tập và đáp án định hướng

### Bài 1 — Vì sao compiler không thấy `s` sau `if`?

~~~java
if (value instanceof String s) {
    System.out.println(s.length());
}
System.out.println(s.length()); // Sai nếu nhánh không match vẫn đi tiếp.
~~~

Đây là **mảnh code có một dòng sai**. Hãy di chuyển dòng dùng `s` vào nhánh đúng hoặc dùng guard clause `if (!(value instanceof String s)) return;` rồi sử dụng `s` ở đường còn lại. Lý do: compiler không thể đảm bảo đã match trên mọi đường tới dòng cuối.

### Bài 2 — So sánh `&&` và `||`

~~~java
if (obj instanceof String s && s.length() > 2) {
    System.out.println(s);
}
~~~

Là mảnh lệnh **hợp lệ** khi `obj` có kiểu thích hợp. Đổi `&&` thành `||` sẽ khiến `s.length()` có thể chạy trên đường pattern **false**, vì vậy **không hợp lệ**.

### Bài 3 — Xử lý generic đúng

Cho `List.of("Java", 2, " ", "API")`. Dùng `instanceof List<?> values`, sau đó dùng `item instanceof String text && !text.isBlank()` để đếm chuỗi không blank. Kết quả **2**. Giải thích vì sao `List<String>` không phải phép kiểm tra hợp lệ đối với nguồn `Object`.

### Bài 4 — Dữ liệu null

Viết phương thức nhận `Object` và trả lần lượt `"missing"` khi null, `"text"` khi là `String`, `"other"` cho kiểu còn lại. Vì sao `null instanceof String s` đánh giá false mà không gọi bất kỳ accessor nào?

### Bài 5 — Chọn tính năng đúng mốc

Với `record Point(int x, int y) {}`, dùng `if (obj instanceof Point point)` và đọc `point.x()`. Giải thích vì sao đây là **type pattern** Java 16, còn `Point(int x, int y)` là **record pattern** Java 21. Đừng dùng cú pháp Java 21 trong chương trình chạy với `--release 17`.

### Bài 6 — Biên dịch và xác nhận stdout

Các ví dụ độc lập có thể chạy lần lượt:

~~~bash
javac --release 17 InstanceofBasicsDemo.java
java InstanceofBasicsDemo

javac --release 17 PatternBranchDemo.java
java PatternBranchDemo

javac --release 17 PatternAndDemo.java
java PatternAndDemo

javac --release 17 GuardClausePatternDemo.java
java GuardClausePatternDemo

javac --release 17 InterfacePatternDemo.java
java InterfacePatternDemo

javac --release 17 GenericPatternDemo.java
java GenericPatternDemo

javac --release 17 RecordTypePatternDemo.java
java RecordTypePatternDemo
~~~

Mỗi tên tệp và `public class` khớp nhau. Các mảnh code được đánh dấu **sai** trong bảng hoặc bài tập dùng để nhận diện compile error, không đem biên dịch độc lập. Nếu cần kiểm thử thật, tạo mỗi file ví dụ theo nội dung đầy đủ ở mục tương ứng.

**Đạt yêu cầu** khi bạn giải thích được: `instanceof Type variable` **chính thức Java 16**; pattern test + bind; flow scoping; khác biệt `&&`/`||`; guard clause; null không match; generic bị giới hạn; type pattern không phải record pattern hay switch pattern.

## 15. Tài liệu chính thức vẫn áp dụng

1. [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): bản chính thức Java 16; biến pattern không còn ngầm `final` và quy tắc test không cần thiết.
2. [Oracle Java 25 — Pattern Matching with instanceof](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-instanceof.html): type pattern, giới hạn scope và ví dụ.
3. [JLS 25 — `instanceof` Operator, `15.20.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2): quy tắc kiểu, giá trị null và phép thử ở runtime.
4. [JLS 25 — Scope for Pattern Variables, `6.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): cơ chế flow scoping, logic `&&`/`||` và phủ định.
5. [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác minh preview ở Java 14/15 và chính thức từ Java 16.
6. [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440) và [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): phân biệt những cú pháp pattern được chính thức hóa ở Java 21.

**Ghi nhớ:** Java 14 đưa ý tưởng pattern matching cho `instanceof` vào thử nghiệm; **Java 16 là mốc chính thức**. Cú pháp `obj instanceof Type variable` gắn **kiểm tra kiểu với biến đã được khởi tạo an toàn**, và compiler chỉ cho dùng biến ở những đường đã match chắc chắn. Dùng JDK đang được cập nhật và phiên bản đích phù hợp, không dựa vào hướng dẫn preview cũ.