# Guarded pattern label là gì trong Java?

> **Module:** Java Core Pattern Matching → Guard when. Bài sử dụng cú pháp **Java 21+**, khi *pattern matching for `switch`* đã được chuẩn hóa (JEP 441). Những đoạn mang chú thích **ERROR** dùng để giải thích lỗi biên dịch, không phải chương trình chạy độc lập. Chương trình đầy đủ và stdout được trình bày ở phần 8.

## Mục tiêu học tập

Sau bài này, bạn sẽ:

- Hiểu **guarded pattern label** là nhãn `case` chứa **pattern** và điều kiện `when`, phân biệt nó với type pattern thường, nhãn hằng và `default`.
- Biết thứ tự: kiểm tra pattern trước, sau đó mới đánh giá guard; guard sai thì `switch` có thể thử nhãn tiếp theo.
- Dùng pattern variable đúng phạm vi bên trong guard và phần thân nhánh, không cast thủ công.
- Sắp xếp nhãn có guard và không có guard để tránh lỗi **dominance**, đồng thời đảm bảo **exhaustiveness** và xử lý `null`.
- Đọc được những tình huống thường gây nhầm: guard hằng `true`/`false`, guard có tác dụng phụ, điều kiện ném ngoại lệ và thứ tự ưu tiên với nhãn hằng.

## 1. Khái niệm và cú pháp chính thức

**Guarded pattern label** (nhãn pattern có điều kiện bảo vệ) là một nhãn `case` có cấu trúc:

~~~text
case Pattern when BooleanExpression -> Result
~~~

Trong đó:

- **`Pattern`**: mô tả kiểu/cấu trúc giá trị selector phải khớp; ví dụ `String text`.
- **`when`**: từ khóa ngữ cảnh đặt điều kiện *guard* ngay sau pattern trong nhãn `case`.
- **`BooleanExpression`**: biểu thức điều kiện trả `boolean` (hoặc giá trị Boolean được unbox thành boolean); có thể dùng biến vừa được pattern bind.
- **`-> Result`**: phần thân nhánh khi cả pattern và guard đều thành công. Với switch statement dạng `:`, cú pháp tương ứng là `case Pattern when BooleanExpression:`.

Ví dụ cơ bản:

~~~java
static String describe(Object input) {
    return switch (input) {
        case String text when text.length() > 5 -> "long text";
        case String text -> "other text";
        default -> "not a string";
    };
}
~~~

Đây là **phương thức minh họa** đặt bên trong lớp Java 21+, chưa phải một tệp có thể chạy độc lập.

Nhãn `case String text when text.length() > 5` có **hai điều kiện cùng phải đúng**:

1. Selector `input` phải match type pattern `String text`.
2. Biến `text` đã được bind, rồi biểu thức `text.length() > 5` phải đánh giá thành `true`.

Nếu `input` là `"abcdef"`, nhánh đầu được chọn. Nếu `input` là `"cat"`, pattern `String` vẫn match nhưng guard sai nên nhánh `case String text` kế tiếp nhận giá trị. Nếu là `Integer.valueOf(3)`, guard `text.length() > 5` **không được chạy** vì bản thân pattern `String` không match.

**Phân biệt thuật ngữ:** `String text` là **type pattern**; cả cụm `case String text when ...` là **guarded pattern label**. `when` không biến biểu thức boolean thành một type pattern mới, và không làm thay đổi kiểu của selector.

## 2. Cơ chế đánh giá một nhãn có `when`

Với `switch (selectorExpression)`, trong trường hợp thông thường Java 21 thực hiện theo thứ tự sau:

1. **Đánh giá selector expression một lần** để lấy giá trị được đem match.
2. Xét các nhãn `case` theo thứ tự đã viết (khi compiler chấp nhận cấu trúc switch).
3. Nếu một type pattern không match, **bỏ qua guard của nhãn đó** và tiếp tục xét nhãn khác.
4. Nếu pattern match, khởi tạo các **pattern variable** rồi đánh giá guard.
5. Nếu guard là `true`, chọn nhánh và thực thi phần thân. Nếu là `false`, tiếp tục thử nhãn phù hợp kế tiếp.
6. Nếu không nhãn nào match, xử lý theo `default` nếu được định nghĩa. `null` là trường hợp đặc biệt và phải xét riêng (phần 6).

Ví dụ:

~~~java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long";
        case String s -> "short nonblank";
        default -> "different type";
    };
}
~~~

| Giá trị selector | Pattern và guard | Kết quả |
| --- | --- | --- |
| `"  "` | Match `String`, `isBlank() == true` | `"blank"` |
| `"Hello"` | Guard đầu sai, guard `length() >= 5` đúng | `"long"` |
| `"Go"` | Hai guard sai, nhãn `String` cuối match | `"short nonblank"` |
| `42` | Không match `String`, không đánh giá các guard `String` | `"different type"` |

**Điểm then chốt:** Một guard trả `false` không có nghĩa toàn bộ `switch` thất bại. Nó chỉ khiến nhãn đó **chưa được chọn** và quá trình kiểm tra có thể tiếp tục.

### Guard ném ngoại lệ có “thử nhãn khác” không?

Không. Nếu biểu thức guard **ném ngoại lệ**, việc xử lý `switch` bị ngắt theo luồng ngoại lệ đó; Java không coi ngoại lệ như một kết quả `false`.

~~~java
static String fragile(Object value) {
    return switch (value) {
        case String s when s.charAt(0) == 'A' -> "starts with A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

Nếu truyền chuỗi rỗng `""`, `s.charAt(0)` ném `StringIndexOutOfBoundsException`. **Không** có chuyện tự chuyển sang nhánh `"other string"`. Cách viết an toàn hơn:

~~~java
case String s when !s.isEmpty() && s.charAt(0) == 'A' -> "starts with A";
~~~

Hoặc ngắn gọn:

~~~java
case String s when s.startsWith("A") -> "starts with A";
~~~

Hai dòng trên là **nhãn minh họa**, cần đặt vào một `switch` hợp lệ có các nhánh khác.

## 3. Pattern variable nằm trong phạm vi của guard

Biến khai báo bởi pattern đã được khởi tạo **trước khi guard chạy**:

~~~java
static String normalize(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> text.trim().toUpperCase();
        case String text -> "(blank)";
        default -> "(not text)";
    };
}
~~~

Trong nhánh đầu, biến `text` có kiểu tĩnh `String` ở **cả guard và biểu thức phía sau `->`**. Không cần ép kiểu `(String) value`.

Hai khai báo `String text` ở hai arm độc lập có thể dùng lại tên `text`, vì scope của pattern variable thuộc nhãn/nhánh tương ứng. Ở nhánh `default` hoặc bên ngoài `switch`, không thể dùng biến `text` đó.

Mã sau **cố ý không biên dịch** khi viết trong một phương thức:

~~~java
String result = switch (value) {
    case String text when text.length() > 3 -> text;
    default -> "other";
};
System.out.println(text); // ERROR: text nằm ngoài scope.
~~~

Giá trị đã xử lý muốn dùng sau `switch` thì lưu **kết quả** vào biến `result`; không truy cập biến pattern của arm đã kết thúc.

### Guard có thể có nhiều điều kiện

~~~java
case String text when !text.isBlank() && text.length() <= 20 -> "valid text";
~~~

Sau `when` là một **biểu thức boolean Java bình thường**. Bạn có thể dùng `&&`, `||`, lời gọi phương thức, phép so sánh, điều kiện dựa trên biến ngoài... miễn là hợp lệ về kiểu và phạm vi. `&&` thực hiện short-circuit như các biểu thức Java khác.

Trong Java 21 chính thức, cách viết chuẩn là:

~~~java
case String text when text.length() > 3 -> "long";
~~~

Đừng sao chép cú pháp guard từ một số bản preview cũ viết điều kiện trực tiếp sau pattern bằng `&&` ngoài `when`. Tuy nhiên, `&&` **ở trong** biểu thức `when` vẫn hoàn toàn hợp lệ.

## 4. Guard giúp chia một kiểu thành các trường hợp cụ thể

Không có guard, cùng một kiểu thường được xử lý bằng `if/else` bên trong một nhánh:

~~~java
static String before(Object input) {
    return switch (input) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank text";
            }
            yield "text: " + s.trim();
        }
        default -> "different type";
    };
}
~~~

Với guard, có thể chuyển từng điều kiện nghiệp vụ thành một nhãn rõ ràng:

~~~java
static String after(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank text";
        case String s -> "text: " + s.trim();
        default -> "different type";
    };
}
~~~

Hai phương thức đều là **mã minh họa trong một lớp Java 21+**, và cả hai trả cùng kết quả với những giá trị `input` không null theo các nhánh đã nêu.

**Vì sao cách sau hữu ích?**

- Nhìn nhãn đã biết điều kiện cần thỏa để vào nhánh; không phải đọc logic `if` ở trong phần thân.
- Phần thân từng nhánh tập trung vào xử lý khi match thành công.
- Có thể đặt nhiều guard cùng kiểu theo thứ tự ưu tiên: trường hợp đặc biệt trước, trường hợp chung sau.

**Không phải mọi `if` đều cần chuyển thành guard.** Nếu điều kiện dài, có nhiều bước hoặc tác dụng phụ, hãy cân nhắc helper boolean có tên rõ nghĩa (và tránh tác dụng phụ) hoặc giữ xử lý bên trong nhánh cho dễ hiểu.

## 5. Thứ tự `case`, dominance và guard hằng

Trong pattern switch, compiler kiểm tra quy tắc **dominance**: không được đặt một nhãn đã bị nhãn trước bao phủ hoàn toàn, khiến nhãn sau không có cơ hội được chọn.

### 5.1. Nhánh không guard đứng trước nhánh có guard: lỗi

~~~java
static String badOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: bị nhánh trên che.
        default -> "other";
    };
}
~~~

Mọi `String` đều đã match `case String s` trước đó. Nhánh `String s when ...` phía sau không thể đến được, nên compiler từ chối.

**Sắp xếp đúng:**

~~~java
static String goodOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "any other string";
        default -> "other";
    };
}
~~~

Tương tự, nếu `case CharSequence cs` không guard đứng trước `case String s when ...`, nhánh sau cũng bị che vì mọi `String` đều là `CharSequence`.

### 5.2. Guard thông thường không được dùng để chứng minh dominance một cách tổng quát

~~~java
static String withGuards(Object value) {
    return switch (value) {
        case String s when s.length() > 5 -> "long";
        case String s when s.startsWith("A") -> "starts with A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

Đoạn này **hợp lệ**, dù hai guard đầu có thể cùng đúng với một giá trị. **Nhãn match đầu tiên được chọn**. Ví dụ `"ABCDEF"` thỏa cả hai guard, nhưng nhánh `"long"` chạy trước.

Compiler không cố giải mọi quan hệ logic của guard tùy ý. Vì vậy, **thứ tự guard quyết định ưu tiên nghiệp vụ**; hai điều kiện có thể chồng nhau mà không bắt buộc báo lỗi dominance.

### 5.3. Ngoại lệ: `when true` và `when false`

Mã sau **cố ý không biên dịch**:

~~~java
static String redundant(Object value) {
    return switch (value) {
        case String s when true -> "any string";
        case String s -> "never reached"; // ERROR: bị dominated.
        default -> "other";
    };
}
~~~

Guard là biểu thức hằng `true` không thu hẹp tập giá trị của pattern; nó có thể dominate nhãn cùng kiểu ở phía sau.

Mã sau cũng **cố ý không biên dịch**, vì guard là biểu thức hằng `false`:

~~~java
static String unreachable(Object value) {
    return switch (value) {
        case String s when false -> "never"; // ERROR: guard hằng false.
        case String s -> "string";
        default -> "other";
    };
}
~~~

Đừng dùng `when true`/`when false` như một cách bật/tắt nhánh; sửa thiết kế `case` hoặc cấu hình điều kiện runtime đúng nghĩa.

### 5.4. Tương tác với nhãn hằng

Đối với `switch` trên `Integer`, một nhánh guarded pattern như `case Integer n when n > 0` có thể match giá trị `1` trước khi tới nhãn hằng `case 1` nếu viết theo thứ tự đó. Compiler thường **không coi một guard tùy ý là chứng cứ dominance** đối với nhãn hằng, dù khi chạy guard có thể nhận giá trị trước.

Để ưu tiên một giá trị đặc biệt, đặt **nhãn hằng trước guard**, rồi tới pattern chung:

~~~java
static String classifyInteger(Integer value) {
    return switch (value) {
        case null -> "null";
        case 1 -> "exactly one";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero or negative";
    };
}
~~~

Đây là **phương thức minh họa** Java 21+. `classifyInteger(1)` trả `"exactly one"`; `classifyInteger(3)` trả `"positive"`; `classifyInteger(-1)` trả `"zero or negative"`. Cách sắp xếp này giúp thứ tự ưu tiên dễ dự đoán.

## 6. Exhaustiveness và xử lý `null`

**Switch expression** và **enhanced switch statement** chứa pattern/`null` cần có đủ nhãn để bao phủ các trường hợp selector có thể thuộc về theo kiểu tĩnh.

Ví dụ sau **cố ý không biên dịch**:

~~~java
static String incomplete(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        // ERROR: còn nhiều String ngắn và vô số Object không phải String.
    };
}
~~~

Một guarded pattern chỉ bao phủ **những giá trị match pattern và đồng thời thỏa guard**. Compiler không xem một guard runtime bất kỳ là đại diện cho mọi giá trị của kiểu selector.

**Sửa bằng fallback phù hợp:**

~~~java
static String complete(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        case String s -> "short text";
        default -> "other";
    };
}
~~~

`case String s` không guard bắt các chuỗi còn lại; `default` bao phủ các đối tượng không null thuộc kiểu khác. Điều này làm `switch` expression exhaustive với những đối tượng không null có thể xuất hiện.

### `null` không match type pattern thông thường

~~~java
static String classifyNullable(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isEmpty() -> "empty";
        case String s -> "text";
        default -> "other";
    };
}
~~~

`case null` là nhãn riêng, **không phải guarded pattern label**. Nếu không có `case null`, một pattern switch thông thường nhận selector `null` sẽ ném `NullPointerException` trước khi `default` nhận được giá trị. `default` không tự động xử lý null.

Có thể dùng `case null, default -> ...` nếu yêu cầu nghiệp vụ muốn gộp hai trường hợp. Tuy nhiên, cách viết `case null -> ...` riêng thường rõ nghĩa hơn khi cần phân biệt dữ liệu thiếu với giá trị không đúng loại.

**Nhớ:** Tính exhaustive của những kiểu tham chiếu không null và xử lý `null` là hai vấn đề khác nhau. Một switch expression được compiler coi là exhaustive vẫn có thể ném `NullPointerException` nếu giá trị selector là null và bạn không khai báo nhánh xử lý.

## 7. Thiết kế guard an toàn và dễ bảo trì

### 7.1. Ưu tiên biểu thức ngắn, không tác dụng phụ

Một guard được đánh giá trong quá trình **chọn nhánh**. Hạn chế đặt cập nhật trạng thái, I/O, thay đổi collection hoặc thao tác phức tạp trong `when`. Những side effect khiến code khó dự đoán khi guard sai và quá trình match chuyển sang nhãn tiếp theo.

~~~java
case String s when s.startsWith("ID-") -> "identifier";
~~~

Cách này dễ hiểu hơn một guard gọi nhiều thao tác rồi sửa trạng thái dùng chung.

### 7.2. Guard phải không ném ngoại lệ ngoài ý muốn

Kiểm tra ranh giới chuỗi hoặc dữ liệu trước khi truy cập phần tử:

~~~java
case String s when s.length() >= 2 && s.charAt(1) == ':' -> "prefixed";
~~~

Nhờ `&&` ngắn mạch, `charAt(1)` không chạy với chuỗi có độ dài dưới 2. Nếu bạn dùng helper trong `when`, hãy mô tả rõ helper có chấp nhận mọi đối tượng thuộc kiểu pattern hay không.

### 7.3. Tránh điều kiện chồng nhau khó đọc

~~~java
case Integer n when n > 0 && n % 2 == 0 -> "positive even";
case Integer n when n > 0 -> "positive odd";
case Integer n -> "nonpositive";
~~~

Nhánh đầu dành cho số dương chẵn, nhánh thứ hai sẽ còn số dương lẻ, và cuối cùng bắt số không dương. Dù guard đầu và guard thứ hai cùng đúng với số chẵn dương theo biểu thức đơn lẻ, **thứ tự nhánh** tạo ra kết quả nhất quán.

### 7.4. Một selector, nhiều guard

Biểu thức trong `switch (expression)` được đánh giá **một lần** để lấy giá trị match. Tuy vậy, có thể có nhiều guard được đánh giá lần lượt nếu các pattern tương ứng match nhưng guard trước là `false`. Vì vậy, đừng nhầm “selector đánh giá một lần” với “chỉ có một điều kiện guard được thử”.

Để chứng minh, chương trình phần 8 đếm số lần đánh giá selector và guard: với đầu vào `"ab"`, selector được gọi đúng một lần và guard được gọi đúng một lần; khi guard sai, nhánh `String` không guard tiếp nhận giá trị.

### 7.5. Nên dùng `when` hay `if` bên trong arm?

Dùng `when` khi điều kiện ngắn và **quyết định nhánh nào phải được chọn**. Giữ `if` trong arm khi sau khi đã chọn kiểu đầu vào bạn cần thực hiện nhiều bước phụ thuộc trạng thái, hoặc tránh tạo quá nhiều nhánh có điều kiện chồng lấn. Không có quy tắc bắt buộc mọi kiểm tra boolean phải chuyển vào `when`.

## 8. Chương trình Java 21 hoàn chỉnh

Lưu toàn bộ mã sau thành **`GuardedLabelDemo.java`**:

~~~java
public class GuardedLabelDemo {
    private static int selectorCalls = 0;
    private static int guardCalls = 0;

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank text";
            case String s when s.length() >= 5 ->
                    "long text: " + s.toUpperCase();
            case String s -> "short text: " + s;

            case Integer n when n > 0 && n % 2 == 0 ->
                    "positive even: " + n;
            case Integer n when n > 0 -> "positive odd: " + n;
            case Integer n -> "nonpositive: " + n;

            default -> "other";
        };
    }

    static Object nextValue() {
        selectorCalls++;
        return "ab";
    }

    static boolean longerThanThree(String text) {
        guardCalls++;
        return text.length() > 3;
    }

    static String probe() {
        return switch (nextValue()) {
            case Integer i -> "integer";
            case String s when longerThanThree(s) -> "long";
            case String s -> "short";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Hello"));
        System.out.println(classify("Go"));
        System.out.println(classify(8));
        System.out.println(classify(7));
        System.out.println(classify(0));
        System.out.println(classify(-2));
        System.out.println(classify(3.14));
        System.out.println(classify(null));

        String result = probe();
        System.out.println(
                "probe=" + result
                + ", selector=" + selectorCalls
                + ", guard=" + guardCalls
        );
    }
}
~~~

Biên dịch/chạy trên **JDK 21 trở lên**, kiểm tra đúng cú pháp nguồn Java 21:

~~~bash
javac --release 21 GuardedLabelDemo.java
java GuardedLabelDemo
~~~

**Stdout chính xác:**

~~~text
blank text
long text: HELLO
short text: Go
positive even: 8
positive odd: 7
nonpositive: 0
nonpositive: -2
other
null
probe=short, selector=1, guard=1
~~~

**Giải thích kết quả:**

1. `"   "`: nhãn `String` đầu match, `isBlank()` đúng → `blank text`.
2. `"Hello"`: guard `isBlank()` sai, guard `length() >= 5` đúng → `long text: HELLO`.
3. `"Go"`: cả hai guard của `String` đều sai → nhãn `case String s` không guard → `short text: Go`.
4. `8`: giá trị `Integer`, dương và chẵn → `positive even: 8`.
5. `7`: guard dương chẵn sai; guard dương đúng → `positive odd: 7`.
6. `0` và `-2`: không vượt qua guard `n > 0`, nhưng match `Integer` cuối → `nonpositive`.
7. `3.14`: kiểu runtime `Double`, không match `String` hoặc `Integer` → `default` → `other`.
8. `null`: nhãn `case null` xử lý trực tiếp.
9. `probe()`: `nextValue()` tạo `"ab"` và tăng `selectorCalls` một lần; pattern `Integer` bị bỏ qua; guard `longerThanThree(s)` được gọi một lần rồi trả `false`; nhánh `String` tiếp theo trả `short`. Không có cast, không đánh giá lại selector.

Chương trình này dùng syntax chuẩn của Java 21; không cần `--enable-preview`.

## 9. Lỗi thường gặp: triệu chứng và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `case String s ->` đặt trước `case String s when condition ->` | Nhánh không guard bao phủ toàn bộ `String`; nhánh sau bị dominance | Đặt nhánh có guard trước |
| `case CharSequence cs ->` trước `case String s when ... ->` | Kiểu tổng quát hơn che kiểu con | Đặt pattern cụ thể hơn trước |
| `case String s when s.length() ->` | `length()` là `int`, không phải boolean | `when s.length() > 0` |
| `case String s when false ->` | Guard là biểu thức hằng `false`; compiler từ chối | Xóa nhánh chết hoặc dùng điều kiện runtime có nghĩa |
| `case String s when true ->` rồi `case String s ->` | Guard hằng `true` không lọc gì; nhánh sau bị dominance | Bỏ guard/hợp nhất nhánh |
| Chỉ có các case có guard cho selector `Object` | Chưa bao phủ mọi đầu vào | Thêm pattern không guard hoặc `default` thích hợp |
| Dùng biến `s` sau khi `switch` kết thúc | Pattern variable đã ngoài scope | Dùng biến kết quả của `switch` |
| Guard gọi `charAt(0)` trên chuỗi rỗng | Guard ném ngoại lệ, không chuyển sang fallback | Kiểm tra `isEmpty()` hoặc dùng `startsWith` |
| Mong `default` bắt `null` | `null` xử lý riêng trong Java 21 pattern switch | Thêm `case null` |
| Sao chép cú pháp preview `case String s && ...` | Cú pháp từ bản preview cũ | Java 21 dùng `case String s when ...` |
| Đặt side effect trong `when` | Điều kiện có thể đánh giá rồi thất bại, khiến tác dụng phụ khó theo dõi | Dùng predicate rõ nghĩa, ít tác dụng phụ |

### Hai ví dụ ERROR riêng biệt

**Sai kiểu của guard** (biên dịch lỗi):

~~~java
static String badGuardType(Object value) {
    return switch (value) {
        case String s when s.length() -> "text"; // ERROR: int không là boolean.
        default -> "other";
    };
}
~~~

**Thiếu nhánh bao phủ** (biên dịch lỗi):

~~~java
static String missingFallback(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        // ERROR: String ngắn và Object khác còn chưa có case.
    };
}
~~~

Các phương thức này là ví dụ minh họa **không được dán vào** lớp demo hoàn chỉnh nếu muốn giữ chương trình chạy được. Việc có `default` để compiler chấp nhận không đảm bảo chương trình xử lý `null` theo nghiệp vụ; vẫn cần `case null` khi có thể nhận null.

## 10. Quy trình đọc/viết một guarded pattern label

Khi gặp `case T t when condition -> branch`, hãy tự hỏi:

1. **Kiểu tĩnh của selector** là gì? Có thể nhận giá trị tương thích `T` không?
2. **Pattern được bind ở đâu?** `t` có kiểu `T` và chỉ tồn tại trong scope của guard và nhánh match.
3. **Guard có an toàn cho mọi giá trị match `T` không?** Có kiểm tra giới hạn trước khi truy cập chỉ số, thao tác chia hay dereference dữ liệu nullable không?
4. **Có nhãn trước bao phủ pattern này không?** Nếu có nhãn không guard cùng kiểu hoặc supertype trước đó, có thể bị compiler báo dominance.
5. **Nếu guard trả `false`, nhãn nào nhận giá trị?** Cần có nhánh cùng kiểu rộng hơn hoặc `default`.
6. **Nếu guard trả `true`, có nhánh hằng/guard ưu tiên hơn đã đặt ở phía trước không?** Thứ tự nhãn ảnh hưởng hành vi.
7. **Nếu selector null thì sao?** Thêm `case null` khi cần.
8. **Switch đã exhaustive chưa?** Compiler phải có cơ sở xác nhận mọi kiểu đầu vào hợp lệ có đường xử lý.

**Ví dụ nhu cầu thực tế:** một tham số `Object payload` có thể nhận chuỗi, số nguyên hoặc kiểu khác. Nếu yêu cầu là “ưu tiên chuỗi trống, rồi chuỗi dài, rồi chuỗi còn lại; với số nguyên, ưu tiên số dương chẵn, rồi số dương lẻ, rồi phần còn lại”, các `case ... when ...` tương ứng rõ ràng hơn một khối nhiều lệnh `if` lồng sâu.

## 11. Bài tập kiểm tra

**Câu 1.** Trong `case String name when name.startsWith("A") -> ...`, điều kiện nào phải đúng để nhánh chạy? `name` tồn tại khi nào và có kiểu gì?

**Câu 2.** Với `switch (Object value)`, ba nhãn theo thứ tự:

~~~java
case String s when s.length() > 4 -> "long";
case String s when s.startsWith("A") -> "starts A";
case String s -> "other string";
~~~

Giá trị `"ABCDEF"` vào nhánh nào? Còn `"Ax"` và `"xy"`?

**Câu 3.** Vì sao compiler từ chối:

~~~java
case String s -> "all";
case String s when s.isBlank() -> "blank";
~~~

**Câu 4.** Tại sao `case String s when s.length() -> ...` sai? Hãy viết lại một guard kiểm tra chuỗi không rỗng.

**Câu 5.** Guard ném ngoại lệ khi truy cập `s.charAt(0)` với chuỗi rỗng. Java có chuyển sang `case String s` ở phía sau không? Cách tránh lỗi là gì?

**Câu 6.** Một `switch` expression trên `Object` chỉ có `case Integer n when n > 0`. Vì sao không biên dịch? Cần thêm loại nhãn nào?

**Câu 7.** `default` đã có. Truyền `null` vào pattern `switch` mà không có `case null` thường xảy ra điều gì trên Java 21?

**Câu 8.** `case Integer i when i > 0` đặt trước `case 1` có nhất thiết bị compiler báo dominance không? Về cách tổ chức ưu tiên, nên đặt nhãn nào trước?

**Câu 9.** Vì sao guard hằng `false` có thể bị từ chối ngay lúc biên dịch, còn một guard phụ thuộc tham số runtime có thể trả `false` mà vẫn hợp lệ?

**Câu 10.** Trong ví dụ `probe()` ở phần 8, vì sao `selectorCalls == 1` và `guardCalls == 1` dù có nhiều nhãn `case`?

### Đáp án gợi ý

1. Selector phải match `String` và `name.startsWith("A")` là `true`. `name` có kiểu `String`, được bind sau khi pattern match, có scope trong guard và arm tương ứng.
2. `"ABCDEF"` vào `"long"` (nhánh đầu tiên, dù cũng bắt đầu bằng A); `"Ax"` vào `"starts A"`; `"xy"` vào `"other string"`.
3. Nhánh không guard đã bắt mọi `String`, nên guarded case phía sau bị **dominated**.
4. `s.length()` là `int`; viết `when !s.isEmpty()` hoặc `when s.length() > 0`.
5. Không. Ngoại lệ từ guard được ném ra; sửa bằng `!s.isEmpty() && s.charAt(0) == 'A'` hoặc `s.startsWith("A")`.
6. Chưa **exhaustive**: còn số không dương, chuỗi và các kiểu khác. Thêm nhánh `Integer` không guard nếu cần, và `default` hoặc pattern tổng quát để bao phủ mọi loại còn lại.
7. Thông thường ném `NullPointerException`; `default` không thay `case null`.
8. Không nhất thiết: guard tổng quát khó phân tích tĩnh, nhưng khi chạy `1` có thể bị guarded case trước nhận mất. Thường đặt `case 1` trước, rồi guarded pattern, rồi pattern không guard.
9. `false` hằng là nhánh chết được biết ngay lúc biên dịch; guard runtime phụ thuộc giá trị đầu vào và có thể đúng ở những lần thực thi khác.
10. Selector expression `nextValue()` chỉ được đánh giá một lần. Guard được gọi một lần do pattern `String` match, còn nhãn `Integer` không match nên không kích hoạt bất kỳ guard nào.

## Nguồn tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), đặc biệt các mục *When Clauses*, *Pattern Label Dominance*, *Type Coverage* và *Scope of Pattern Variable Declarations*.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế cuối cùng và cú pháp `when` được chuẩn hóa trong JDK 21.
- [Java Language Specification 21 — `14.11 The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): cú pháp `case`, guard, dominance và yêu cầu bao phủ.
- [Java Language Specification 21 — `15.28 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): ngữ nghĩa switch expression và tính exhaustive.
- [Java Language Specification 21 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi pattern variable trong guard và nhánh.
