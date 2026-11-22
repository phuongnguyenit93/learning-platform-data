# Cú pháp pattern kết hợp when trong Java 21

## 1. Guard when dùng để làm gì?

Khi dùng pattern matching trong `switch`, một pattern chỉ xác nhận **kiểu hoặc hình dạng dữ liệu**. Nhiều tình huống còn cần điều kiện bổ sung: chuỗi không được rỗng, số phải dương, tọa độ phải thuộc một vùng, hoặc hai thành phần record phải thỏa một quan hệ. Trong Java 21, viết **guard** với từ khóa ngữ cảnh `when` ngay sau case pattern:

~~~java
case String text when !text.isBlank() -> "TEXT:" + text;
~~~

Một nhãn `case` như vậy có **hai điều kiện nối tiếp**:

1. Giá trị trong `switch (expression)` phải khớp **pattern** `String text`. Nếu không khớp, Java không đánh giá guard.
2. Sau khi khớp và gắn biến `text`, Java đánh giá **guard** `!text.isBlank()`. Chỉ khi guard trả về `true` thì case này mới được chọn.

Nếu guard trả về `false`, Java tiếp tục tìm một nhãn `case` khác có thể khớp. Điều này khác với việc nhánh đã được chọn rồi trả về `false`; **guard quyết định chọn nhánh, không phải là giá trị trả về của nhánh**.

Mục tiêu bài học:

- Viết đúng `case Pattern when booleanExpression -> ...` và dạng dấu hai chấm `case Pattern when booleanExpression:`.
- Biết vị trí đặt `when` và kiểu kết quả cần có của guard.
- Sử dụng pattern variable an toàn trong guard và phần code của case.
- Kết hợp guard với type pattern, record pattern và pattern lồng nhau.
- Phân tích thứ tự các nhãn, dominance, `default`, `null` và yêu cầu exhaustive của switch expression.
- Nhận diện lỗi biên dịch khi guard không phải boolean, đặt guard lên nhãn không có pattern hoặc đặt nhãn bao quát trước nhãn có guard.

**Phiên bản:** bài này sử dụng cú pháp chính thức của **Java 21+** (JEP 441, Pattern Matching for switch). Có thể dùng JDK 21 hoặc mới hơn và lệnh `javac --release 21`, **không cần `--enable-preview`**. Cú pháp trong các bản preview của Java 17–20 đã thay đổi theo quá trình phát triển, vì vậy không sao chép nguyên cú pháp `when` của Java 21 để mong biên dịch với `--release 17`.

## 2. Công thức cú pháp: case pattern rồi mới when

Dạng mũi tên dùng trong switch expression hoặc switch statement:

~~~java
switch (value) {
    case String s when s.isBlank() -> System.out.println("Blank");
    case String s -> System.out.println("String: " + s);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
~~~

Đây là **đoạn mã minh họa** bên trong phương thức có biến `Object value`. Công thức cơ bản:

~~~text
case <pattern> when <boolean-expression> -> <expression-or-statement>
case <pattern> when <boolean-expression> :  <statement-group>
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `case` | Bắt đầu nhãn lựa chọn |
| `String s` hoặc `Point(int x, int y)` | Pattern kiểm tra đối tượng và giới thiệu biến |
| `when` | Đánh dấu điều kiện bảo vệ (*guard*) bổ sung |
| `s.isBlank()`, `x > 0 && y > 0` | Biểu thức điều kiện, phải tương thích với `boolean` |
| `->` | Bắt đầu một switch rule, không fall-through |
| `:` | Bắt đầu statement group dạng truyền thống; cần kiểm soát fall-through |

Cú pháp đặt `when` **sau pattern nhưng trước `->` hoặc dấu `:`**. Không viết guard vào trong phần pattern như thể nó là một component, và không nhầm biểu thức sau `->` với điều kiện guard.

Ví dụ đúng:

~~~java
case Integer number when number > 0 -> "POSITIVE";
case Integer number -> "ZERO_OR_NEGATIVE";
~~~

Ví dụ dùng record pattern (Java 21):

~~~java
case Point(int x, int y) when x == y -> "SAME_COORDINATES";
~~~

Các đoạn trên là nhãn minh họa, không phải chương trình độc lập; muốn chạy cần đặt trong `switch` có selector kiểu phù hợp và, với ví dụ record, có khai báo `record Point(int x, int y) {}`.

**Giới hạn cú pháp:** `when` là guard của **case pattern**. Không thể gắn trực tiếp guard cho nhãn chỉ chứa hằng hay nhãn `null`:

~~~java
case "yes" when true -> 1;  // KHÔNG HỢP LỆ trên Java 21
case null when true -> 1;   // KHÔNG HỢP LỆ trên Java 21
~~~

Hai dòng trên **cố ý không biên dịch**. Nếu muốn áp dụng điều kiện phụ cho một giá trị kiểu `String`, thường dùng `case String s when ...` và viết logic cho trường hợp hằng cụ thể ngay trong guard nếu phù hợp; còn `case "yes"` riêng thì không cần guard để so khớp chính hằng đó.

## 3. Cách Java chọn một case có guard

Giả sử có:

~~~java
return switch (value) {
    case String s when s.isBlank() -> "BLANK";
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "SHORT";
    default -> "OTHER";
};
~~~

Đây là một trích đoạn trong phương thức có tham số `Object value` và kiểu trả về `String`.

Quy trình xét các nhãn theo thứ tự:

1. Java đánh giá selector `value` và xét các case theo thứ tự hợp lệ trong switch block.
2. Với nhãn `case String s when s.isBlank()`, nếu giá trị không phải `String` thì bỏ qua guard và xét tiếp. Nếu là `String` thì gắn `s` rồi gọi `isBlank()`.
3. Nếu guard đúng, chọn case này, thực thi rule body sau `->` và hoàn tất switch expression.
4. Nếu guard sai, tiếp tục thử case kế tiếp. Một giá trị `"hello"` không blank nhưng có 5 ký tự, nên khớp `case String s when s.length() >= 5`.
5. Nếu hai guard trước đều sai nhưng giá trị vẫn là `String`, nhãn `case String s` không guard xử lý phần còn lại.
6. Nếu không phải `String`, nhãn `default` xử lý các giá trị khác phù hợp; `null` cần được cân nhắc riêng.

**Guard không được dùng để kiểm tra kiểu trước pattern.** Câu hỏi đầu tiên luôn là pattern có khớp không; guard chỉ chạy sau khi pattern đã gắn được các biến. Với `null`, type pattern `String s` không khớp nên guard `s.isBlank()` không được gọi.

Sự khác biệt về kết quả:

| Giá trị của selector | Pattern và guard | Rule được chọn |
| --- | --- | --- |
| `"   "` | `String s` khớp, `s.isBlank()` đúng | `"BLANK"` |
| `"hello"` | Guard thứ nhất sai, guard `length() >= 5` đúng | `"LONG"` |
| `"hi"` | Cả hai guard sai, pattern `String s` chung khớp | `"SHORT"` |
| `12` | Không khớp các pattern `String` | `"OTHER"` |

Guard trả `false` **không** có nghĩa chương trình tự chạy phần code phía sau `->` rồi dừng ở đó. Java tiếp tục chọn nhãn phù hợp ở phía sau.

## 4. Chương trình đầy đủ: nhiều guard trên cùng loại String và Integer

Lưu tệp `GuardWhenSyntaxDemo.java`:

~~~java
public class GuardWhenSyntaxDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG:" + s;
            case String s -> "SHORT:" + s;
            case Integer n when n > 0 -> "POS:" + n;
            case Integer n when n == 0 -> "ZERO";
            case Integer n -> "NEG:" + n;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("hello"));
        System.out.println(classify("hi"));
        System.out.println(classify(7));
        System.out.println(classify(0));
        System.out.println(classify(-3));
        System.out.println(classify(1.5));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 GuardWhenSyntaxDemo.java
java GuardWhenSyntaxDemo
~~~

Kết quả chính xác:

~~~text
NULL
BLANK
LONG:hello
SHORT:hi
POS:7
ZERO
NEG:-3
OTHER
~~~

Phân tích:

- `case String s when s.isBlank()` xử lý các chuỗi chỉ chứa khoảng trắng; `"   "` cho `BLANK`.
- `case String s when s.length() >= 5` xử lý chuỗi đủ dài **sau khi đã loại chuỗi blank** bằng nhãn phía trên; `"hello"` cho `LONG:hello`.
- `case String s` là case dự phòng cho những chuỗi không qua các guard trước; `"hi"` cho `SHORT:hi`.
- Ba nhãn `Integer n` cùng phân loại số nguyên dương, không, âm. `n` được gắn riêng trong từng case và có kiểu `Integer`.
- `1.5` là giá trị `Double` khi boxing vào `Object`, nên không khớp `Integer n` và rơi vào `default`.

Cú pháp lặp tên `s` hay `n` trong các case riêng không có nghĩa là một biến duy nhất tồn tại xuyên tất cả nhánh. Mỗi pattern variable có phạm vi phù hợp với **nhãn của nó**.

## 5. Phạm vi pattern variable trong guard và rule body

Đặc điểm tiện lợi của `when` là có thể dùng ngay biến vừa được pattern giới thiệu:

~~~java
case String text when text.length() > 3 -> text.toUpperCase();
~~~

Java không cho phép tham chiếu `text` từ guard nếu pattern không đưa biến đó vào phạm vi. Ở ví dụ hợp lệ này:

- Pattern `String text` khớp thì `text` được gắn với đối tượng `String`.
- `text.length()` là lời gọi hợp lệ trong biểu thức guard và có kiểu `int`; phép so sánh `> 3` tạo `boolean`.
- Khi guard đúng, rule body `text.toUpperCase()` được phép đọc `text`.
- Khi guard sai, rule body không chạy; Java tiếp tục xét case khác.

### Pattern mới xuất hiện bên trong guard

Guard là một biểu thức Java thực sự nên có thể dùng thêm `instanceof` với pattern variable, miễn tuân thủ quy tắc flow scoping:

~~~java
case CharSequence cs
    when cs instanceof String text && text.length() >= 3 ->
    "LONG_TEXT:" + text.toUpperCase();
~~~

Đây là **đoạn trích** trong switch selector có kiểu `Object`. `cs` do case pattern `CharSequence cs` giới thiệu. Guard thử xem chính `cs` có phải `String` hay không rồi gắn thêm `text`. Nhờ `&&` short-circuit, `text.length()` chỉ được gọi nếu phép `instanceof String text` thành công. Khi **toàn guard đúng**, `text` cũng được dùng trong rule body.

Để kiểm tra đầy đủ, lưu `GuardInnerPatternScopeDemo.java`:

~~~java
public class GuardInnerPatternScopeDemo {
    static String classify(Object value) {
        return switch (value) {
            case CharSequence cs
                    when cs instanceof String text && text.length() >= 3 ->
                "LONG_TEXT:" + text.toUpperCase();
            case CharSequence cs -> "OTHER_CHARSEQ:" + cs.length();
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("Hi"));
        System.out.println(classify(new StringBuilder("hello")));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardInnerPatternScopeDemo.java
java GuardInnerPatternScopeDemo
~~~

Kết quả:

~~~text
LONG_TEXT:JAVA
OTHER_CHARSEQ:2
OTHER_CHARSEQ:5
NULL
~~~

Cần phân biệt ba trường hợp:

1. `"Java"`: khớp `CharSequence cs`; guard xác nhận `cs instanceof String text` và có ít nhất 3 ký tự; rule đầu được chọn.
2. `"Hi"`: khớp kiểu `CharSequence` và `String`, nhưng `text.length() >= 3` sai; Java chuyển sang case `CharSequence cs` không guard.
3. `new StringBuilder("hello")`: khớp `CharSequence` nhưng **không** khớp `String text` trong guard; vế phải `text.length()` của `&&` không chạy và case chung xử lý.

Không thể sử dụng `text` ở rule `case CharSequence cs` khác hay ngoài switch chỉ vì cùng một giá trị có thể từng được thử ở guard trước đó.

## 6. when với record pattern: kiểm tra hình dạng và điều kiện thành phần

**Record pattern** cho phép tách các component của một record ngay khi khớp. Guard `when` sau đó có thể xét mối quan hệ giữa các component.

Ví dụ:

~~~java
case Point(int x, int y) when x == y -> "EQUAL:" + x;
~~~

Trong đó `Point(int x, int y)` là record pattern; các biến `x`, `y` được gắn nếu record có dạng phù hợp. Guard `x == y` chỉ được xét sau khi record pattern đã khớp.

Chương trình đầy đủ lưu `GuardWhenRecordDemo.java`:

~~~java
record Point(int x, int y) {}

public class GuardWhenRecordDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case Point(int x, int y) when x == y -> "EQUAL:" + x;
            case Point(int x, int y) when x > 0 && y > 0 ->
                "POSITIVE:" + x + "," + y;
            case Point(int x, int y) -> "POINT:" + x + "," + y;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Point(3, 3)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(new Point(-2, 4)));
        System.out.println(classify("no"));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenRecordDemo.java
java GuardWhenRecordDemo
~~~

Kết quả:

~~~text
EQUAL:3
POSITIVE:2,5
POINT:-2,4
OTHER
~~~

Giải thích:

- `Point(3, 3)` khớp guard `x == y`; trả `EQUAL:3`.
- `Point(2, 5)` không khớp guard bằng nhau, nhưng thỏa `x > 0 && y > 0`; trả `POSITIVE:2,5`.
- `Point(-2, 4)` không thỏa hai guard, nhưng vẫn khớp cấu trúc record `Point`; đi tới nhãn `case Point(int x, int y)` không guard.
- `"no"` không phải `Point`; đi tới `default`.

**Pattern chịu trách nhiệm giải cấu trúc**, còn `when` diễn tả điều kiện nghiệp vụ bổ sung. Không cần ép kiểu record thủ công hay gọi accessor `x()`, `y()` để lấy dữ liệu trong những nhánh pattern đã khớp. Với record pattern lồng nhau, guard có thể tham chiếu các biến component đã được gắn trong pattern đó nếu hợp lệ theo phạm vi.

## 7. when còn kết hợp được với phương thức trả boolean

Guard không nhất thiết là phép so sánh đơn. Có thể gọi một phương thức kiểm tra nghiệp vụ, miễn lời gọi tạo ra một điều kiện Boolean hợp lệ.

Lưu `GuardWhenMethodDemo.java`:

~~~java
public class GuardWhenMethodDemo {
    static boolean accepted(String s) {
        return s.length() >= 4 &&
               s.chars().allMatch(Character::isLetter);
    }

    static String label(Object value) {
        return switch (value) {
            case String s when accepted(s) -> "ACCEPT:" + s;
            case String s -> "REJECT:" + s;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label("a2b4"));
        System.out.println(label("abc"));
        System.out.println(label(23));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenMethodDemo.java
java GuardWhenMethodDemo
~~~

Kết quả:

~~~text
ACCEPT:Java
REJECT:a2b4
REJECT:abc
OTHER
~~~

Ở đây `accepted(s)` chỉ chạy **sau khi** `case String s` khớp. Nó trả về `true` khi chuỗi dài ít nhất 4 ký tự và tất cả ký tự là chữ cái. Các chuỗi không thỏa điều kiện đi tới nhãn `case String s` thứ hai.

Trong thực tế:

- Nên dùng hàm guard thuần, dễ hiểu, không gây tác dụng phụ không cần thiết; guard có thể bị đánh giá khi Java đang tìm nhãn khớp.
- Guard có thể gọi hàm, dùng `&&`, `||`, `!` và dấu ngoặc để diễn đạt logic nhưng phải trả về `boolean` hoặc một giá trị có thể dùng như `boolean` theo quy tắc unboxing của Java.
- Nếu guard ném ngoại lệ, switch **không** tự coi đó là `false` và chuyển sang case kế tiếp; ngoại lệ lan ra theo luồng thực thi bình thường.
- Tránh code vừa thay đổi đối tượng vừa kiểm tra đối tượng trong guard vì điều đó làm thứ tự nhánh khó dự đoán và dễ tạo lỗi.

## 8. Guard when cũng dùng được với dấu hai chấm

Cú pháp guard không bị giới hạn ở `->`. Với **switch statement group** truyền thống, có thể viết:

~~~java
case String s when s.isBlank():
    return "BLANK";
~~~

Lưu chương trình đầy đủ `GuardWhenColonDemo.java`:

~~~java
public class GuardWhenColonDemo {
    static String classify(Object value) {
        switch (value) {
            case null:
                return "NULL";
            case String s when s.isBlank():
                return "BLANK";
            case String s when s.length() > 3:
                return "LONG";
            case String s:
                return "SHORT";
            default:
                return "OTHER";
        }
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("Hi"));
        System.out.println(classify(null));
        System.out.println(classify(1));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenColonDemo.java
java GuardWhenColonDemo
~~~

Kết quả:

~~~text
BLANK
LONG
SHORT
NULL
OTHER
~~~

Điểm khác biệt nằm ở **cú pháp và luồng điều khiển của switch body**, không nằm ở ý nghĩa của guard:

- Guard ở dạng `case Pattern when condition:` vẫn được đánh giá sau khi pattern khớp.
- Các câu lệnh sau dấu `:` tạo thành một statement group; biến pattern dùng được trong group tương ứng.
- Dạng dấu hai chấm có khả năng *fall-through* khi code trước nhãn tiếp theo hoàn tất bình thường. Ví dụ trên dùng `return` ở mọi nhánh để không rơi xuống nhánh khác.
- Java còn hạn chế việc fall-through **vào** một nhãn khai báo pattern variable vì biến đó có thể chưa được khởi tạo nếu không thực sự khớp pattern.
- Dạng `case ... ->` thường dễ kiểm soát hơn vì không fall-through, nhất là khi xử lý nhiều nhãn có guard.

**Đừng đổi `case ... when ... ->` thành `case ... :` rồi bỏ hết `return`/`break`** nếu điều đó làm luồng thực thi rơi qua nhãn tiếp theo.

## 9. Thứ tự nhãn, dominance và nhánh dự phòng

Hai case sau có thứ tự hợp lý:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "STRING";
~~~

Nhãn đầu dành cho trường hợp đặc biệt, nhãn sau bao quát mọi `String` còn lại.

Đảo lại sẽ gây lỗi biên dịch:

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK"; // COMPILE ERROR: dominated
~~~

Nhánh `String s` không guard đứng trước đã khớp mọi giá trị `String`. Nhánh sau không còn cơ hội được chọn; compiler báo `this case label is dominated by a preceding case label`. Đây là **đoạn cố ý không hợp lệ**, không phải mã chạy.

Các nguyên tắc thiết kế:

- Đặt các pattern có guard cụ thể **trước** pattern tổng quát của cùng kiểu.
- Đặt subtype trước supertype khi cần phân biệt, ví dụ `case Integer n when n > 0` trước `case Number n`.
- Bổ sung một case cùng kiểu **không guard** hoặc `default` cho những giá trị không thỏa điều kiện nếu cần.
- Đừng giả định Java sẽ tự chọn nhánh “cụ thể nhất” độc lập với thứ tự case.
- Nếu hai guard có miền điều kiện giao nhau, case đứng trước sẽ được ưu tiên khi cả hai cùng có thể đúng.

### Guard không thay thế exhaustive coverage

Một switch expression phải bao phủ mọi giá trị có thể cần xử lý. Dù selector tĩnh là `String`, nhãn duy nhất:

~~~java
case String s when s.length() > 3 -> 1;
~~~

**không** bao phủ các chuỗi ngắn hơn. Với switch expression thiếu các nhãn khác, Java sẽ báo lỗi không exhaustive. Cần thêm `case String s -> ...`, `default` hoặc một thiết kế bao phủ hợp lệ.

Đối với selector kiểu `Object`, một `default` thường cần thiết để xử lý các kiểu không khớp pattern. Một switch có thể được compiler xem là exhaustive nhờ một mẫu không guard bao trùm kiểu selector hoặc nhờ tập subtype sealed đã được bao phủ, tùy quy tắc Java 21.

## 10. when không phải cách xử lý null

Type pattern `String s` không khớp giá trị `null`; do đó `when s.isBlank()` không được đánh giá khi selector là `null`. Tuy nhiên, đối với switch trên tham chiếu null, bạn cần quyết định riêng liệu sẽ xử lý null hay để ngoại lệ xảy ra.

Ví dụ:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

Đoạn minh họa này nằm trong một phương thức có `Object value`, kiểu trả về `String`.

- `case null` khớp `null`.
- `case String s when ...` không khớp `null`; guard không được gọi.
- `default` đứng riêng **không tự coi là nhánh bắt null** trong pattern switch.

Vì vậy, `case null when ...` không phải cách viết hợp lệ. Nếu muốn mọi null bị từ chối, có thể viết `case null -> throw new IllegalArgumentException("null");` hoặc kiểm tra null trước switch.

### Guard Boolean và ngoại lệ

Nếu guard dựa trên phương thức có thể ném lỗi, lỗi đó không bị biến thành kết quả `false`. Tương tự, nếu dùng một giá trị `Boolean` trong ngữ cảnh cần `boolean`, việc unboxing từ `null` có thể gây `NullPointerException`. Khi thiết kế guard, ưu tiên biểu thức kiểm tra đơn giản, rõ ràng và không đưa vào các giá trị Boolean nullable chưa được kiểm tra.

## 11. Các lỗi biên dịch điển hình về when

Các đoạn sau là **mã cố ý không biên dịch** đã được thử bằng `javac --release 21`. Chúng mô tả lỗi để giúp tự kiểm tra cú pháp, không phải các chương trình chạy được.

### Lỗi 1 — Guard không phải boolean

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s when s.length() -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

`s.length()` trả `int`, không phải điều kiện `boolean`. Compiler báo:

~~~text
error: incompatible types: int cannot be converted to boolean
~~~

Sửa bằng một phép so sánh hoặc phương thức trả boolean, ví dụ `s.length() > 3`.

### Lỗi 2 — Guard trên nhãn hằng

~~~java
static int invalid(String value) {
    return switch (value) {
        case "yes" when true -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

Compiler báo:

~~~text
error: guards are only allowed for case with a pattern
~~~

Nhãn `case "yes"` là nhãn hằng, không phải type pattern hoặc record pattern. Dùng `case "yes" -> 1` trực tiếp, hoặc dùng pattern `case String s when ...` nếu điều kiện cần dựa trên biến pattern.

### Lỗi 3 — Guard trên case null

~~~java
static int invalid(Object value) {
    return switch (value) {
        case null when true -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

Compiler cũng báo `guards are only allowed for case with a pattern`. Dùng `case null -> 1` riêng.

### Lỗi 4 — Nhánh có guard bị nhánh trước bao trùm

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> 1;
        case String s when s.isEmpty() -> 2; // COMPILE ERROR
        default -> 0;
    };
}
~~~

Compiler báo nhãn bị `dominated`. Đổi thứ tự để kiểm tra `isEmpty()` trước pattern chung.

### Lỗi 5 — Dùng biến của nhánh guard ở nhánh khác

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> 1;
        case Integer n -> s.length(); // COMPILE ERROR
        default -> 0;
    };
}
~~~

`s` không tồn tại trong scope của nhánh `Integer`. Compiler báo `cannot find symbol: variable s`. Mỗi nhánh cần dùng biến do chính pattern của nó khai báo hoặc một biến khác có phạm vi hợp lệ.

### Lỗi 6 — Chỉ có một case có guard mà thiếu nhánh khác

~~~java
static int invalid(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> 1;
    };
}
~~~

Compiler báo:

~~~text
error: the switch expression does not cover all possible input values
~~~

Một chuỗi có độ dài 0, 1, 2 hoặc 3 không thỏa guard. Cần thêm nhánh xử lý chúng, ví dụ `case String s -> 0`; với null, tùy hợp đồng runtime mà cân nhắc `case null`.

## 12. Checklist sử dụng when an toàn

Khi đọc một case pattern có guard, hãy tự hỏi:

1. Dự án đang biên dịch bằng **Java 21+** hay một bản preview có cú pháp khác?
2. Nhãn có thực sự chứa **pattern** ngay trước `when` không?
3. Guard có kiểu `boolean` hợp lệ không?
4. Mọi pattern variable được sử dụng trong guard đã được gắn bởi pattern hoặc một biểu thức con theo quy tắc flow scoping chưa?
5. Guard có đơn giản và hạn chế tác dụng phụ/ngoại lệ không?
6. Các nhánh cụ thể có đứng **trước** pattern bao quát để tránh dominance không?
7. Nếu guard trả `false`, Java sẽ xét tiếp nhánh nào? Có nhánh không guard dự phòng không?
8. Switch expression có exhaustive không, và giá trị `null` được xử lý theo đúng yêu cầu không?
9. Nếu dùng cú pháp `case ...:`, có tránh fall-through sai vào case có pattern variable chưa?
10. Có phân biệt **guard chọn nhánh** và **expression/statement của nhánh** chưa?

## 13. Bài tập và đáp án

### Bài 1 — Xác định nhánh

Cho:

~~~java
static String label(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() > 4 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

Kết quả của `label("   ")`, `label("hello")`, `label("hi")` và `label(5)` là gì?

**Đáp án:** Lần lượt là `BLANK`, `LONG`, `SHORT` và `OTHER`. Hai guard đứng trước được thử theo thứ tự nếu pattern `String` khớp.

### Bài 2 — when với record pattern

Với `record Range(int start, int end) {}`, viết nhãn case nhận diện một range hợp lệ có `start <= end` và trả `"VALID"`.

**Đáp án tham khảo:**

~~~java
case Range(int start, int end) when start <= end -> "VALID";
~~~

Đây là đoạn nhãn đặt trong switch thích hợp, không phải chương trình độc lập. Cần thêm case cho `Range` không thỏa guard và các kiểu khác nếu switch expression yêu cầu exhaustive.

### Bài 3 — Vì sao null không gọi isBlank?

Tại sao `switch (value)` với `case String s when s.isBlank()` không gây `NullPointerException` ở guard khi `value == null`?

**Đáp án:** Vì type pattern `String s` không khớp `null` nên guard chưa được đánh giá. Tuy nhiên, **bản thân switch** trên `null` vẫn cần nhãn `case null` hoặc xử lý thích hợp, nếu không có thể ném `NullPointerException`.

### Bài 4 — Sửa guard sai kiểu

Sửa:

~~~java
case String s when s.length() -> "LONG";
~~~

**Đáp án:** Thêm điều kiện Boolean, ví dụ `case String s when s.length() >= 5 -> "LONG";`.

### Bài 5 — Đảo thứ tự case

Giải thích vì sao:

~~~java
case Number n -> "NUMBER";
case Integer i when i > 0 -> "POSITIVE_INTEGER";
~~~

là cách đặt nhãn không hợp lệ khi selector cho phép cả `Number` và `Integer`.

**Đáp án:** `Integer` là subtype của `Number`. Nhãn `case Number n` không guard đã bao trùm các đối tượng `Integer`, khiến nhãn `Integer i` phía sau bị dominated. Đặt nhãn `Integer i when i > 0` trước `Number n`.

### Bài 6 — Guard có pattern bên trong

Đoạn sau hợp lệ hay không và tại sao?

~~~java
case CharSequence cs
    when cs instanceof String text && text.length() >= 3 ->
    "LONG:" + text;
~~~

**Đáp án:** Hợp lệ trên Java 21 khi selector cho phép áp dụng `CharSequence`. Guard chỉ đánh giá sau khi `cs` được gắn; `&&` bảo đảm `text.length()` chỉ chạy sau khi `cs instanceof String text` khớp. Khi guard đúng, `text` ở trong phạm vi rule body.

## 14. Ghi nhớ và tài liệu tham khảo

**Công thức cốt lõi:**

~~~text
case Pattern p when booleanConditionUsing(p) -> branch
~~~

Java kiểm tra **pattern trước, guard sau**. Guard đúng thì chọn nhánh và chạy phần code của nhánh; guard sai thì tìm nhãn tiếp theo. Cần đặt trường hợp cụ thể trước trường hợp chung, giữ điều kiện trả về `boolean`, hiểu đúng phạm vi biến, xử lý `null` và bảo đảm switch expression có đủ nhánh.

Tài liệu chính thức để đọc thêm:

- JLS Java SE 21 `14.11.1 — Switch Blocks, guarded case labels và dominance: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- JLS Java SE 21 `6.3.3 — Scope for Pattern Variables in case Labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
