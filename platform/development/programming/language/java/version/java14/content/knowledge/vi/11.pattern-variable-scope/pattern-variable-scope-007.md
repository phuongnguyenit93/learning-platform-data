# Xung đột tên và khai báo mẫu ở các nhánh độc lập

## 1. Vấn đề cần giải quyết

Khi dùng **pattern matching cho `instanceof`**, Java cho phép kết hợp kiểm tra kiểu và khai báo biến mẫu (*pattern variable*) trong một biểu thức:

~~~java
if (input instanceof String value) {
    System.out.println(value.length());
}
~~~

Ở đây `value` có kiểu `String` và **chỉ được sử dụng ở những vị trí mà trình biên dịch biết chắc phép so khớp đã thành công**. Quy tắc này gọi là **flow scoping** — phạm vi phụ thuộc vào luồng điều khiển, không chỉ vào cặp ngoặc nhọn.

Vì vậy, hai khai báo biến mẫu cùng tên có thể:
- **Hợp lệ** nếu nằm ở những nhánh hoặc vùng phạm vi **không chồng lấn**.
- **Bị từ chối khi biên dịch** nếu tên mới trùng một biến cục bộ đang trong phạm vi hoặc hai khai báo cùng tên cùng xuất hiện trong một biểu thức với quy tắc xung đột.
- **Có phạm vi kéo dài sau câu lệnh `if`** khi các đường đi khác đã kết thúc bằng `return` hoặc `throw`; điều này ảnh hưởng tới khả năng khai báo lại tên sau đó.

Đề bài của chương này là phân biệt rõ **“cùng tên”** với **“trùng phạm vi”**: trong Java, có thể dùng lại một tên ở nhánh độc lập, nhưng không được dựa vào cảm giác rằng các điều kiện “loại trừ nhau” để khai báo tùy ý.

**Phiên bản và tính hiện hành:** Pattern matching cho `instanceof` có trong Java 14 dưới dạng preview, đã trở thành tính năng **chính thức từ Java 16 (JEP 394)** và tiếp tục dùng trong Java hiện đại. Ví dụ chính sử dụng **Java 17+ không cần `--enable-preview`**. Phần mở rộng riêng về pattern matching trong `switch` dùng cú pháp **Java 21+** đã được chuẩn hóa, tuyệt đối không nhầm với `switch` theo mẫu ở các bản preview cũ.

## 2. Tại sao pattern variable có phạm vi khác biến cục bộ thông thường?

Biến cục bộ thông thường có phạm vi gắn với khối khai báo:

~~~java
void example() {
    String name = "A"; // Có hiệu lực trong khối phương thức.
    if (true) {
        System.out.println(name); // Đọc được biến bên ngoài.
    }
}
~~~

Biến mẫu chỉ xuất hiện khi **đã so khớp thành công**, ví dụ:

~~~java
void inspect(Object input) {
    if (input instanceof String text) {
        System.out.println(text.toUpperCase());
    } else {
        // text không ở trong phạm vi ở nhánh else.
    }
    // text cũng không mặc định ở trong phạm vi sau if.
}
~~~

Hai đoạn trên là **mã minh họa phương thức**, không phải một chương trình độc lập có `main`.

Điều kiện `input instanceof String text` chỉ tạo giá trị cho `text` khi `input` là một `String`. Đối với `input == null` hoặc kiểu khác, phép so khớp không thành công, vì vậy không thể cho phép truy cập `text` trên đường đi đó.

### 2.1. Khái niệm “definitely matched”

Đặc tả Java sử dụng khái niệm **definitely matched** để xác định nơi một pattern variable có thể được dùng. Với `input instanceof String text`, biến `text` chắc chắn đã được gán khi **biểu thức trả `true`**. Trong biểu thức phủ định `!(input instanceof String text)`, biến `text` lại chắc chắn đã khớp khi **biểu thức phủ định trả `false`**.

Nhờ đó, compiler biết biến nào tồn tại ở từng đoạn của `if`, `else`, `&&`, `||` và một số câu lệnh điều khiển khác.

**Lưu ý:** Flow scoping không giống Java tự động làm cho tên biến ở mọi nhánh đều có thể truy cập. Compiler chỉ cho phép sử dụng một pattern variable tại những điểm có chứng cứ rằng **chính khai báo đó** đã khớp và được khởi tạo.

## 3. Hai nhánh độc lập dùng cùng tên: hợp lệ

### 3.1. Trong chuỗi `if / else if`

~~~java
static String describe(Object input) {
    if (input instanceof String value) {
        return "Text: " + value.length();
    } else if (input instanceof Integer value) {
        return "Number: " + value;
    } else if (input instanceof java.util.List<?> value) {
        return "List: " + value.size();
    }
    return "Unknown";
}
~~~

Đây là **phương thức độc lập về mặt cú pháp**, cần được đặt trong lớp Java. Cả ba pattern đều khai báo tên `value` nhưng **không xung đột**:

1. Ở nhánh `String`, `value` là `String`, được dùng để lấy độ dài.
2. Ở nhánh `Integer`, `value` là `Integer`, được dùng như số.
3. Ở nhánh `List<?>`, `value` là `List<?>`, được dùng để đếm phần tử.
4. Mỗi khai báo thuộc phạm vi của **nhánh khớp tương ứng**. Không có thời điểm nào cả ba khai báo `value` cùng ở trong phạm vi và bị tham chiếu theo cách mơ hồ.

**Tên giống nhau không có nghĩa là cùng một biến.** Chúng là ba pattern variable khác nhau, mỗi biến có kiểu và điểm khai báo riêng. Không thể lấy `value` của nhánh `String` đem dùng trong nhánh `Integer` hoặc sau toàn bộ chuỗi `if`.

Trong code nghiệp vụ dài, cân nhắc tên mô tả kiểu/nội dung như `text`, `count` hoặc `items` để tránh nhầm lẫn. Dùng cùng tên hữu ích khi mọi nhánh biểu diễn cùng vai trò “giá trị vừa khớp”, nhưng **không phải bắt buộc**.

### 3.2. Hai câu lệnh `if` liên tiếp cũng có thể dùng cùng tên

~~~java
static void independent(Object left, Object right) {
    if (left instanceof String item) {
        System.out.println(item.toUpperCase());
    }
    if (right instanceof Integer item) {
        System.out.println(item + 1);
    }
}
~~~

Đoạn trên hợp lệ: cả hai `if` là những phép so khớp độc lập. Biến mẫu `item` của `if` thứ nhất **không còn trong phạm vi** khi bước sang `if` thứ hai, vì sau `if` đầu tiên vẫn có đường đi bình thường mà việc so khớp `String` thất bại.

Một sai lầm thường gặp là nghĩ “tên `item` đã xuất hiện trong cùng phương thức nên không được dùng lại”. Với pattern variable, phải xét **phạm vi theo luồng điều khiển**, không chỉ xét từ đầu đến cuối tệp.

### 3.3. Cũng có thể dùng lại tên trong nhánh `else`

~~~java
static void print(Object input) {
    if (input instanceof String label) {
        System.out.println("Text: " + label);
    } else {
        String label = "fallback"; // Hợp lệ: tên pattern không ở scope tại đây.
        System.out.println(label);
    }
}
~~~

`label` của nhánh `then` chỉ xuất hiện khi `instanceof` đúng, còn `label` được khai báo trong `else` là một biến cục bộ **khác**. Vì các phạm vi không chồng lấn, trình biên dịch cho phép.

**Không suy luận ngược:** không phải mọi nhánh `else` đều tự động độc lập; nếu điều kiện phức tạp hoặc có phép phủ định, cần xét phạm vi theo đúng biểu thức. Ví dụ `if (!(input instanceof String label)) ... else ...` thì biến mẫu `label` có thể có phạm vi trong **nhánh `else`**, không phải nhánh `then`.

## 4. Khi tên đang trong phạm vi: xung đột thực sự

### 4.1. Đụng tên biến cục bộ khai báo từ trước

~~~java
// KHÔNG HỢP LỆ: ví dụ cố ý gây lỗi biên dịch.
static void invalid(Object input) {
    String text = "outer";
    if (input instanceof String text) {
        System.out.println(text);
    }
}
~~~

Biến cục bộ `text` đã tồn tại tại vị trí `instanceof String text`. Java không cho pattern variable **che khuất một biến cục bộ khác đang trong phạm vi** theo cách này. Trình biên dịch báo lỗi vì biến `text` đã được định nghĩa.

**Cách sửa 1 — đổi tên pattern variable:**

~~~java
static void valid(Object input) {
    String text = "outer";
    if (input instanceof String matchedText) {
        System.out.println(matchedText);
    }
    System.out.println(text);
}
~~~

**Cách sửa 2 — giảm phạm vi biến cũ**, bằng cách tổ chức lại thành các khối độc lập có mục đích rõ ràng. Không nên thêm ngoặc tùy tiện nếu vẫn làm hai tên chồng phạm vi.

### 4.2. Đụng tên một biến khai báo bên trong nhánh đã khớp

~~~java
// KHÔNG HỢP LỆ: ví dụ cố ý gây lỗi.
static void invalidNested(Object input) {
    if (input instanceof String matched) {
        String matched = "another"; // Tên đã ở trong scope của nhánh.
        System.out.println(matched);
    }
}
~~~

Trong nhánh `then`, `matched` của pattern đã khớp và ở trong phạm vi. Khai báo thêm một biến cục bộ trùng tên trong chính nhánh này không hợp lệ.

**Cách sửa:** dùng trực tiếp `matched` hoặc đặt tên khác nếu thực sự cần biến mới:

~~~java
static void validNested(Object input) {
    if (input instanceof String matched) {
        String normalized = matched.trim();
        System.out.println(normalized);
    }
}
~~~

### 4.3. Trường của đối tượng khác biến cục bộ

Không phải mọi khai báo trùng tên đều gây lỗi. Pattern variable có thể **che khuất field** trong phần phạm vi nó có hiệu lực:

~~~java
class Holder {
    private final String label = "field";

    void show(Object input) {
        if (input instanceof String label) {
            System.out.println(label);      // Pattern variable.
            System.out.println(this.label); // Field của đối tượng.
        }
    }
}
~~~

Đoạn trên là một lớp hợp lệ. `this.label` truy cập field, trong khi `label` đơn lẻ truy cập pattern variable khi đã match. Tuy nhiên, để mã dễ đọc, nên dùng tên mô tả như `matchedLabel`; không nên cố tình cho nhiều ý nghĩa cùng một tên nếu không cần.

**Kết luận nhỏ:** Không thể chỉ nhìn thấy “hai tên giống nhau” rồi kết luận hợp lệ hay không. Phải biết **loại khai báo** (local/pattern/field), **phạm vi có chồng nhau không** và **cách tham chiếu**.

## 5. `&&`: biến mẫu hợp lệ ở vế phải, nhưng không thể khai báo trùng tên

`&&` đánh giá vế phải chỉ khi vế trái là `true`. Vì vậy biến mẫu ở vế trái có thể được sử dụng ở vế phải:

~~~java
static boolean nonBlank(Object input) {
    return input instanceof String text && !text.isBlank();
}
~~~

`text` được phép trong `!text.isBlank()` vì khi vế phải được đánh giá, `input instanceof String text` chắc chắn đã khớp.

Nhưng hai pattern **cùng tên** trong một `&&` là lỗi:

~~~java
// KHÔNG HỢP LỆ: hai khai báo pattern cùng tên trong một &&.
static boolean invalidAnd(Object left, Object right) {
    return left instanceof String item && right instanceof String item;
}
~~~

Bên phải `&&` nằm trên đường mà pattern `item` ở vế trái đã khớp; khai báo tiếp `item` đè lên biến đang ở trong phạm vi, nên biên dịch thất bại.

**Sửa bằng tên khác:**

~~~java
static boolean validAnd(Object left, Object right) {
    return left instanceof String leftText
            && right instanceof String rightText
            && leftText.equals(rightText);
}
~~~

Với `&&`, cả hai biến `leftText` và `rightText` đều được sử dụng hợp lệ sau khi từng điều kiện trước đó khớp.

## 6. `||`: hai điều kiện khác nhau không đồng nghĩa hai biến mẫu độc lập

Một lỗi khó phát hiện:

~~~java
// KHÔNG HỢP LỆ: không được khai báo cùng tên ở cả hai nhánh của ||.
static boolean invalidOr(Object a, Object b) {
    return a instanceof String value || b instanceof String value;
}
~~~

Mặc dù `a` và `b` là hai đối tượng và `||` chỉ cần một vế đúng, Java vẫn **cấm hai khai báo pattern cùng tên ở hai toán hạng của cùng biểu thức `||`**. Đây là quy tắc xung đột rõ ràng của đặc tả; ngay cả khi không dùng `value` ở phần thân sau đó, khai báo cũng không hợp lệ.

Khác với hai câu lệnh `if` độc lập, hai vế `||` nằm **bên trong một biểu thức hợp nhất**. Khi kết quả là `true`, không thể bảo đảm biến nào trong các pattern đó đã được khởi tạo. Vì vậy không có một `value` chung cho toàn bộ nhánh.

**Sửa đơn giản nhất khi chỉ cần kiểm tra:**

~~~java
static boolean eitherString(Object a, Object b) {
    return a instanceof String || b instanceof String;
}
~~~

**Nếu cần sử dụng cả hai giá trị theo vai trò riêng**, có thể tách thành hai nhánh `if`:

~~~java
static String firstString(Object a, Object b) {
    if (a instanceof String text) {
        return text;
    }
    if (b instanceof String text) {
        return text;
    }
    return "";
}
~~~

Hai pattern `text` ở đây độc lập, mỗi đường `return` của nhánh chỉ sử dụng biến đã khớp. Điều này hợp lệ và dễ giải thích hơn cố gắng hợp nhất hai khai báo cùng tên vào `||`.

### 6.1. Không dùng pattern variable của vế trái ở vế phải `||`

~~~java
// KHÔNG HỢP LỆ:
static boolean invalidOrAccess(Object input) {
    return input instanceof String text || text.isBlank();
}
~~~

Vế phải `||` chỉ chạy khi điều kiện trái là **`false`** — chính là lúc pattern `String text` **chưa khớp**. Vì thế `text` không ở trong phạm vi để đọc tại đó.

Khi muốn thực hiện thêm điều kiện trên một chuỗi đã khớp, dùng `&&`:

~~~java
static boolean isShortText(Object input) {
    return input instanceof String text && text.length() < 5;
}
~~~

Còn nếu chỉ cần biểu diễn hai điều kiện thay thế, tách các điều kiện và sử dụng giá trị bên trong nhánh chắc chắn đã khớp.

## 7. Phủ định `!`, guard clause và phạm vi kéo dài

Phạm vi biến mẫu không nhất thiết kết thúc ngay sau dấu `}` của một `if`. Ví dụ:

~~~java
static String upper(Object input) {
    if (!(input instanceof String text)) {
        return "not-text";
    }
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

Nếu điều kiện `!(input instanceof String text)` đúng, phương thức `return` ngay. Vì vậy **mọi đường đi đến lệnh sau `if`** đều là đường mà phép so khớp `String text` đã thành công. Java cho phép sử dụng `text` tới hết phần còn lại của phạm vi phù hợp.

### 7.1. Xung đột do tưởng biến đã hết scope

~~~java
// KHÔNG HỢP LỆ: text vẫn trong scope sau guard.
static String invalidGuard(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Must be text");
    }
    String text = "new"; // Khai báo lại bị trùng.
    return text;
}
~~~

Đây là lỗi khác với hai `if` độc lập. Vì nhánh thất bại **không thể hoàn thành bình thường** (`throw`), biến `text` được xem là đã khớp tại lệnh ngay sau `if`. Tên của nó tiếp tục có hiệu lực, nên không được khai báo một local `text` khác ở đây.

**Cách sửa:** dùng lại `text`; nếu cần biến xử lý trung gian, dùng tên khác:

~~~java
static String validGuard(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Must be text");
    }
    String normalized = text.strip();
    return normalized;
}
~~~

### 7.2. Đối chiếu với `if` có hai đường đi bình thường

~~~java
static String reuseAfterIf(Object input) {
    if (input instanceof String name) {
        System.out.println("Matched: " + name);
    }
    String name = "after-if"; // Hợp lệ.
    return name;
}
~~~

Dòng `String name = "after-if"` hợp lệ vì đường đi khi `input` **không phải `String`** vẫn đi tới cuối `if`. Trình biên dịch không thể kết luận biến mẫu `name` đã khớp trên mọi đường sau `if`, nên pattern variable này không được đưa vào phạm vi sau `if`.

**Bài học:** Giữa hai ví dụ `invalidGuard` và `reuseAfterIf`, sự khác biệt chính là **luồng điều khiển**, không phải số dấu ngoặc nhọn.

## 8. Chương trình chạy được: tên giống nhau trên các nhánh độc lập

Lưu nguyên mã sau vào tệp **`PatternNameBranchesDemo.java`**. Ví dụ chỉ dùng cú pháp chính thức từ Java 16 và biên dịch với `--release 17`.

~~~java
import java.util.List;
import java.util.Locale;

public final class PatternNameBranchesDemo {
    static String classify(Object input) {
        if (input instanceof String value) {
            return "String:" + value.length();
        } else if (input instanceof Integer value) {
            return "Integer:" + (value * 2);
        } else if (input instanceof List<?> value) {
            return "List:" + value.size();
        }
        return "Other";
    }

    static String independent(Object first, Object second) {
        String result = "";
        if (first instanceof String item) {
            result += "left=" + item.toUpperCase(Locale.ROOT);
        }
        if (second instanceof Integer item) {
            result += " right=" + (item + 1);
        }
        return result.trim();
    }

    static String earlyExit(Object input) {
        if (!(input instanceof String text)) {
            return "not-text";
        }
        return "text=" + text.toUpperCase(Locale.ROOT);
    }

    static String chained(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "nonempty=" + text;
        }
        return "blank-or-not-string";
    }

    static String scopeEnds(Object input) {
        if (input instanceof String name) {
            System.out.println("Matched: " + name);
        }
        String name = "after-if";
        return name;
    }

    public static void main(String[] args) {
        System.out.println(classify("hello"));
        System.out.println(classify(7));
        System.out.println(classify(List.of("a", "b")));
        System.out.println(classify(2.5));
        System.out.println(independent("java", 4));
        System.out.println(earlyExit("ok"));
        System.out.println(earlyExit(10));
        System.out.println(chained("yes"));
        System.out.println(chained(""));
        System.out.println(scopeEnds("first"));
    }
}
~~~

Lệnh biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 PatternNameBranchesDemo.java
java PatternNameBranchesDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
String:5
Integer:14
List:2
Other
left=JAVA right=5
text=OK
not-text
nonempty=yes
blank-or-not-string
Matched: first
after-if
~~~

### 8.1. Giải thích các điểm quan trọng

- `classify("hello")`: nhánh `String value`, lấy `value.length() == 5`.
- `classify(7)`: nhánh `Integer value`, nhân `7 * 2 == 14`.
- `classify(List.of("a", "b"))`: nhánh `List<?> value`, số phần tử là `2`.
- `classify(2.5)`: không khớp ba loại, trả `Other`.
- `independent("java", 4)`: hai phép kiểm tra `if` khác nhau đều khớp, mỗi phép có biến `item` **riêng**, tạo `left=JAVA right=5`. Đây là minh chứng rằng tên biến mẫu có thể được khai báo lại khi **phạm vi cũ đã kết thúc**.
- `earlyExit("ok")`: đường không phải chuỗi đã bị loại bởi `return`, nên `text` có thể dùng ở phần tiếp theo. Với số `10`, trả `not-text`.
- `chained("yes")`: `&&` cho phép dùng `text` ở vế phải; chuỗi không rỗng nên kết quả `nonempty=yes`.
- `chained("")`: pattern `String text` vẫn khớp nhưng `!text.isBlank()` sai, nên kết quả `blank-or-not-string`.
- `scopeEnds("first")`: pattern `name` chỉ ở nhánh đầu; biến cục bộ `String name` mới ở sau `if` không xung đột, trả `after-if`.

**Đã kiểm tra:** toàn bộ tệp này biên dịch bằng `javac --release 17` và chạy ra đúng 11 dòng trên.

## 9. Java 21+: pattern variable cùng tên ở các nhánh `switch`

Phần này là **mở rộng hiện đại, không yêu cầu Java 17**. Pattern matching cho `switch` trở thành tính năng chính thức từ **Java 21 (JEP 441)**; cú pháp `case String item` và `when` dưới đây chạy với `--release 21`, không cần `--enable-preview`.

Các **switch rule** tách biệt có thể khai báo pattern variable cùng tên, vì mỗi biến có phạm vi ở guard và nhánh đi kèm của **chính case đó**:

~~~java
public final class PatternSwitchBranchesDemo {
    static String label(Object input) {
        return switch (input) {
            case String item when !item.isBlank() -> "Text:" + item.length();
            case String item -> "Blank";
            case Integer item -> "Integer:" + item;
            case null -> "Null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label(""));
        System.out.println(label(8));
        System.out.println(label(null));
        System.out.println(label(1.5));
    }
}
~~~

Biên dịch/chạy trên **JDK 21 trở lên**:

~~~bash
javac -encoding UTF-8 --release 21 PatternSwitchBranchesDemo.java
java PatternSwitchBranchesDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Text:4
Blank
Integer:8
Null
Other
~~~

Giải thích:

- `case String item when !item.isBlank()`: biến `item` có hiệu lực trong **`when`** và biểu thức sau `->`. Với chuỗi `"Java"`, in `Text:4`.
- `case String item ->`: khai báo một **biến khác**, dù cùng tên `item`. Trường hợp chuỗi rỗng được xử lý ở đây.
- `case Integer item ->`: khai báo biến `item` kiểu `Integer` cho một case riêng.
- `case null` và `default` không được dùng `item` ở các case phía trên.

**Không nhầm với Java 17:** `case String item` chưa là cú pháp `switch` được chuẩn hóa của Java 17. Nếu dự án dùng Java 17, hãy sử dụng chuỗi `if/else if` với `instanceof` như ở phần 8.

**Không lạm dụng trường hợp same-name:** Nếu case label bị **dominated** bởi một pattern tổng quát đứng trước, nó vẫn là lỗi dù đặt tên khác. Ví dụ `case CharSequence text` đứng trước `case String text` không hợp lệ, vì mọi chuỗi `String` đều đã được bắt bởi `CharSequence`. Với dạng `case ...:` theo nhóm câu lệnh, còn có quy tắc ngăn fall-through tới nhánh pattern có biến chưa được khởi tạo; để nội dung dễ hiểu, ví dụ ở đây dùng **arrow rules `->`**.

## 10. Phân biệt các tình huống qua bảng nhanh

| Tình huống | Có thể dùng cùng tên? | Vì sao? |
| --- | --- | --- |
| `if (o instanceof String s) ... else if (o instanceof Integer s) ...` | **Có** | Hai nhánh khớp có phạm vi biến mẫu không chồng lấn |
| Hai `if` liên tiếp, mỗi `if` có `instanceof ... s` và cùng hoàn thành bình thường | **Có** | `s` thứ nhất không ở trong phạm vi tại `if` thứ hai |
| Khai báo biến local `String s` trong nhánh `else` của `if (o instanceof String s)` | **Có** | Pattern `s` không có hiệu lực trong nhánh `else` ấy |
| Sau `if (o instanceof String s) { ... }`, khai báo local `String s` | **Có**, khi không có quy tắc khác kéo dài phạm vi | Phép match không chắc chắn đúng ở đoạn sau |
| Đã có local `String s` ở ngoài, rồi `if (o instanceof String s)` | **Không** | Pattern trùng tên local đang trong phạm vi |
| Trong nhánh `if (o instanceof String s)` khai báo thêm local `String s` | **Không** | Scope của pattern bao trùm nhánh |
| `a instanceof String s && b instanceof String s` | **Không** | Pattern `s` ở vế trái đang trong scope của vế phải |
| `a instanceof String s || b instanceof String s` | **Không** | `||` cấm hai toán hạng giới thiệu pattern cùng tên |
| `a instanceof String s && !s.isEmpty()` | **Có** | Vế phải chỉ chạy sau khi `s` đã khớp |
| Sau `if (!(o instanceof String s)) return;`, khai báo local `String s` | **Không** | `s` đã chắc chắn khớp nên vẫn trong scope |
| Java 21+: `case String s -> ...` và `case Integer s -> ...` | **Có** | Hai switch rule độc lập |
| Pattern `s` che khuất field `this.s` | **Có thể** | Pattern variable có thể shadow field, không được shadow local đang scope |

Bảng này diễn tả **các trường hợp được giả định đúng theo cấu trúc nêu ở từng dòng**; mọi chương trình vẫn phải tuân thủ type checking và các điều kiện hợp lệ khác của Java.

## 11. Quy trình xác định xung đột tên khi đọc code

Khi code có hai lần viết `instanceof Type name` hoặc `case Type name`, hãy kiểm tra theo thứ tự:

1. **Xác định phiên bản Java.** Dùng `instanceof` pattern chính thức từ Java 16; `switch` pattern chính thức từ Java 21. Đừng coi một cú pháp preview lịch sử là API hiện tại.
2. **Xác định biểu thức khai báo pattern** và đường điều khiển mà nó chắc chắn đã khớp. Với `instanceof` trực tiếp là nhánh `true`; với `!` thì đảo lại.
3. **Xác định chỗ đang xét có nằm trong phạm vi khai báo trước không**: nhánh `then`, vế phải `&&`, sau guard `return/throw`, hoặc case rule tương ứng.
4. **Xác định có biến cục bộ/parameter đã tồn tại cùng tên không.** Nếu có trong phạm vi, đừng khai báo pattern cùng tên.
5. **Kiểm tra xung đột nội tại của một biểu thức `&&`, `||` hoặc `?:`.** Không suy diễn “hai vế loại trừ nhau” là đủ; đặc tả còn quy định rõ các tên pattern bị cấm khi hai toán hạng cùng giới thiệu.
6. **Nếu hai nhánh thật sự độc lập**, có thể dùng cùng tên, nhưng cân nhắc tên rõ nghĩa để giảm nhầm lẫn khi bảo trì.
7. **Không cố dùng pattern variable ngoài phạm vi**; nếu cần mang dữ liệu ra xa hơn, hãy tạo biến kết quả có kiểu và cách gán rõ ràng trên mọi đường đi.

Đặc biệt, **một dấu ngoặc đóng không luôn đánh dấu hết phạm vi pattern**. Guard clauses có `return`/`throw` có thể kéo dài phạm vi đó sang các lệnh theo sau.

## 12. Lỗi phổ biến và hướng khắc phục

### Lỗi A — Dùng biến mẫu trong nhánh `else` sai

~~~java
// KHÔNG HỢP LỆ:
if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println(text); // Không có text từ pattern ở đây.
}
~~~

**Sửa:** chỉ dùng `text` trong nhánh chắc chắn khớp; ở `else` xử lý `input` gốc hoặc tạo biến khác.

### Lỗi B — Xem pattern ở `if` như local biến tồn tại tới cuối phương thức

~~~java
// KHÔNG HỢP LỆ:
if (input instanceof String text) {
    System.out.println(text.length());
}
System.out.println(text); // Phần này có thể được tới khi không khớp.
~~~

**Sửa:** đặt logic cần `text` bên trong nhánh đã khớp hoặc dùng guard clause để loại bỏ đường không khớp trước khi dùng `text` ở phía sau.

### Lỗi C — Khai báo biến trùng tên trong một `&&`

~~~java
// KHÔNG HỢP LỆ:
if (a instanceof String s && b instanceof String s) {
    System.out.println(s);
}
~~~

**Sửa:** dùng hai tên `leftString`, `rightString` và truy cập mỗi biến ở đường đi hợp lệ.

### Lỗi D — Khai báo tên lặp trong `||` rồi tưởng Java chọn một biến

~~~java
// KHÔNG HỢP LỆ:
if (a instanceof String s || b instanceof String s) {
    System.out.println("At least one String");
}
~~~

Cả hai pattern cùng tên trong biểu thức vẫn bị từ chối dù không gọi `s` trong thân. **Sửa:** chỉ kiểm tra kiểu nếu không cần biến, hoặc tách thành hai `if` độc lập.

### Lỗi E — Đặt biến local cùng tên ngay sau guard `throw`

~~~java
// KHÔNG HỢP LỆ:
if (!(input instanceof String text)) {
    throw new IllegalArgumentException();
}
String text = "fallback"; // Trùng pattern đang có phạm vi.
~~~

**Sửa:** dùng `text` đã match hoặc đổi tên thành `fallback` / `normalized`.

### Lỗi F — Nhầm xung đột local với shadowing field

~~~java
class Example {
    String code = "field";

    void run(Object input) {
        if (input instanceof String code) {
            System.out.println(code);      // Pattern variable.
            System.out.println(this.code); // Field.
        }
    }
}
~~~

Đoạn trên **hợp lệ**; nếu tên `code` đã là **local** trong phương thức thay vì field thì kết luận có thể khác. **Sửa về mặt thiết kế:** nên đặt pattern `matchedCode` nếu việc trùng tên khiến người đọc khó nhận ra.

### Lỗi G — Dùng mẫu `switch` của Java 21 trên cấu hình Java 17

~~~java
// Chỉ dành cho Java 21+, KHÔNG phải Java 17:
return switch (input) {
    case String s -> s.length();
    default -> 0;
};
~~~

**Sửa:** dùng `if (input instanceof String s)` trên Java 17, hoặc biên dịch nhắm Java 21+ khi toàn bộ hệ thống hỗ trợ. Không dựa vào các cờ preview cũ.

## 13. Bài tập và lời giải

### Bài 1 — Xác định phạm vi

Cho đoạn mã minh họa trong một phương thức:

~~~java
if (left instanceof String v) {
    System.out.println(v.length());
}
if (right instanceof Integer v) {
    System.out.println(v + 1);
}
~~~

**Câu hỏi:** Có lỗi khai báo `v` hai lần không? Vì sao?

**Đáp án:** **Không**, với cấu trúc trên hai câu `if` độc lập và biến mẫu `v` của câu trước không ở trong phạm vi tại câu sau. Mỗi nhánh chỉ truy cập biến của chính lần match tương ứng.

### Bài 2 — Sửa xung đột tên trong `&&`

Đoạn sau không biên dịch:

~~~java
if (left instanceof String value && right instanceof String value) {
    System.out.println(value);
}
~~~

Hãy sửa để in tổng độ dài hai chuỗi khi cả hai đều là `String`.

**Đáp án:**

~~~java
if (left instanceof String leftText
        && right instanceof String rightText) {
    System.out.println(leftText.length() + rightText.length());
}
~~~

Hai pattern khác tên; vế phải và phần thân `if` chỉ được đánh giá khi phép match trước đó thành công.

### Bài 3 — Chọn phạm vi đúng với guard clause

~~~java
static int count(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length();
}
~~~

**Câu hỏi:** Dòng cuối có hợp lệ không? Có thể thêm `String text = "new";` ngay trước dòng cuối không?

**Đáp án:** Dòng cuối **hợp lệ**. Không được khai báo `String text` trùng tên ở đó: mọi đường đi tới cuối phương thức đã đi qua phép match thành công và pattern `text` vẫn ở trong phạm vi.

### Bài 4 — Tư duy về `||`

Bạn muốn trả về chuỗi đầu tiên trong hai `Object` nếu là `String`, hoặc trả về `"<none>"` nếu không có chuỗi nào. Hãy tránh dùng hai pattern cùng tên trong một `||`.

**Đáp án:**

~~~java
static String firstText(Object a, Object b) {
    if (a instanceof String text) {
        return text;
    }
    if (b instanceof String text) {
        return text;
    }
    return "<none>";
}
~~~

Mỗi biến `text` chỉ thuộc phạm vi của một nhánh riêng. Khi `a` không phải `String`, việc so khớp `b` diễn ra độc lập. Không có biến nào được dùng trước khi match.

## 14. Tóm tắt kiến thức cần nhớ

- **Flow scoping** quyết định phạm vi của biến mẫu dựa vào việc phép match **chắc chắn thành công** ở đường đi hiện tại.
- Trong **`if / else if`** và các **`if` liên tiếp độc lập**, có thể khai báo cùng tên pattern variable khi phạm vi không chồng lấn.
- Không khai báo pattern variable trùng với một **local variable hoặc parameter đang trong phạm vi**, cũng không khai báo local trùng pattern ngay trong nhánh mà pattern đang có hiệu lực.
- `&&` cho phép **sử dụng** biến của vế trái ở vế phải sau khi match, nhưng không cho hai pattern cùng tên xung đột.
- `||` **không cho** hai toán hạng giới thiệu pattern cùng tên; điều kiện đúng cũng không bảo đảm biến từ vế nào đã khởi tạo để dùng ở thân.
- Phủ định `!` và **early return/throw** có thể làm pattern variable **tiếp tục có phạm vi sau `if`**.
- Với Java **21+**, pattern variables ở các **case rules độc lập** của `switch` có thể dùng cùng tên; chú ý `when`, phạm vi case và quy tắc dominance.
- Luôn ưu tiên tên dễ hiểu và code đơn giản; chỉ dùng lại cùng một tên khi nó làm logic thực sự rõ hơn.

**Nguồn đặc tả chính thức:**
- [Java Language Specification SE 17 — `6.3, Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): quy tắc “definitely matched”, `&&`, `||`, `if` và phạm vi biến mẫu.
- [Java Language Specification SE 17 — `6.4, Shadowing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): phân biệt local name conflicts và field shadowing.
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): tính năng `instanceof` pattern chính thức từ Java 16.
- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): phạm vi pattern ở nhánh `case`, `when`, các quy tắc Java 21.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): phiên bản chính thức của pattern `switch` từ Java 21.
