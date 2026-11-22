# Kiểu kết quả của biểu thức điều kiện và chuyển kiểu có thể xảy ra — Java 17+

## 1. Toán tử `?:` không chỉ chọn một trong hai giá trị

Biểu thức điều kiện (*conditional expression*, thường gọi toán tử ba ngôi) có cú pháp:

~~~java
condition ? whenTrue : whenFalse
~~~

Java **đánh giá `condition` trước**, rồi **chỉ đánh giá nhánh được chọn**. Đồng thời, compiler xác định **kiểu của toàn biểu thức** theo quy tắc của Java: kiểu đó không nhất thiết giống kiểu của giá trị ở nhánh đang chạy.

~~~java
boolean chooseFirst = true;
double value = chooseFirst ? 10 : 2.5;

System.out.println(value); // 10.0
~~~

Nhánh `10` là literal `int`, nhánh `2.5` là literal `double`. Vì đây là **biểu thức điều kiện số**, Java suy ra kiểu kết quả `double` và chuyển 10 thành `10.0`. Việc nhánh `2.5` **không chạy** không ngăn kiểu của nó ảnh hưởng đến kiểu chung.

**Phân biệt ba câu hỏi:**

1. **Nhánh nào được chạy?** Phụ thuộc kết quả boolean của `condition`.
2. **Kiểu biểu thức là gì?** Do quy tắc kiểu tại compile time; cần xem cả hai nhánh và đôi khi cả ngữ cảnh đích.
3. **Có chuyển kiểu nào?** Có thể gồm numeric promotion, narrowing đặc biệt, boxing/unboxing hoặc reference conversion.

## 2. Ba nhóm biểu thức điều kiện

Java phân loại `?:` theo kiểu của hai nhánh:

| Nhóm | Nhánh 2 và 3 | Ví dụ | Đặc điểm |
|---|---|---|---|
| **Boolean conditional** | `boolean`/`Boolean` phù hợp | `flag ? true : false` | Kết quả logic; có thể unbox wrapper |
| **Numeric conditional** | Hai kiểu số hoặc wrapper số phù hợp | `flag ? 1 : 2L` | Có quy tắc chọn kiểu số và chuyển kiểu |
| **Reference conditional** | Các trường hợp reference/null thích hợp | `flag ? "OK" : null` | Có thể chịu **target typing** trong ngữ cảnh gán/lời gọi |

Java 17 có các quy tắc chi tiết theo cặp kiểu cụ thể; **không thể luôn nói “toán tử `?:` lấy kiểu lớn hơn”**. Với `byte`/`short` và hằng `int`, có ngoại lệ quan trọng. Với kiểu tham chiếu, ngữ cảnh đích cũng có thể quyết định việc biểu thức có hợp lệ không.

~~~mermaid
flowchart TD
    A["condition ? expr1 : expr2"] --> B{"Hai nhánh là boolean/Boolean?"}
    B -- "Có" --> C["Boolean conditional expression"]
    B -- "Không" --> D{"Hai nhánh là kiểu số phù hợp?"}
    D -- "Có" --> E["Numeric conditional expression"]
    D -- "Không" --> F["Reference conditional expression"]
    C --> G["Kiểm tra chọn nhánh và unboxing có thể xảy ra"]
    E --> H["Kiểm tra numeric promotion/narrowing đặc biệt"]
    F --> I["Kiểm tra kiểu tham chiếu và target typing"]
~~~

**Điều kiện đầu** phải có kiểu `boolean` hoặc `Boolean` có thể unbox. Java không tự coi một số khác 0 là true:

~~~java
// int number = 1;
// int result = number ? 10 : 20; // LỖI COMPILE: condition không là boolean
~~~

## 3. Chỉ nhánh được chọn mới được đánh giá

~~~java
static int trace(String label, int value) {
    System.out.println("evaluated " + label);
    return value;
}
~~~

Nếu:

~~~java
boolean flag = true;
int selected = flag
        ? trace("true", 7)
        : trace("false", 9);

System.out.println(selected);
~~~

**Expected stdout:**

~~~text
evaluated true
7
~~~

Nhánh false **không chạy**: không gọi method, không phát sinh side effect hoặc exception trong nhánh đó.

Tuy nhiên, compiler vẫn **kiểm tra kiểu cả hai nhánh**. Một nhánh không bao giờ chạy theo dữ liệu ví dụ vẫn không được chứa biểu thức sai kiểu:

~~~java
// int wrong = true ? 10 : "text";
// Không thể gán reference conditional này cho int theo quy tắc kiểu Java.
~~~

**Lưu ý:** việc loại bỏ nhánh runtime không giống loại bỏ nhánh khỏi kiểm tra kiểu tại compile time.

## 4. Kiểu số thông thường: `int`, `long`, `float`, `double`

Với hai nhánh số phổ biến:

~~~java
boolean flag = true;

var first = flag ? 10 : 20;    // int
var second = flag ? 10 : 20L;  // long
var third = flag ? 10 : 2.5;   // double
var fourth = flag ? 10 : 2.5f; // float
~~~

| Hai nhánh | Kiểu biểu thức | Giá trị khi `flag == true` |
|---|---|---|
| `10` và `20` | `int` | `10` |
| `10` và `20L` | `long` | `10L` |
| `10` và `2.5f` | `float` | `10.0f` |
| `10` và `2.5` | `double` | `10.0` |

Với những cặp kiểu này, chuyển kiểu số học thích hợp làm hai nhánh tương thích với kiểu kết quả.

**Đừng suy kiểu bằng kiểu biến nhận:** ví dụ dưới đây có hai bước khác nhau:

~~~java
double d = flag ? 1 : 2;
~~~

Bản thân `flag ? 1 : 2` là biểu thức số kiểu **`int`**; phép gán sau đó mở rộng giá trị sang `double`. Ngược lại, `flag ? 1 : 2.0` có kiểu **`double` ngay ở biểu thức điều kiện**.

## 5. Ngoại lệ đặc biệt: `byte`/`short` và hằng `int` vừa miền

Java có quy tắc đặc biệt khi một nhánh là `byte`, `short` hoặc wrapper tương ứng và nhánh kia là **hằng `int` biểu diễn được trong kiểu nhỏ**.

~~~java
boolean flag = true;
byte small = 10;

var within = flag ? small : 100;  // byte
var outside = flag ? small : 1000; // int
~~~

- `100` là **hằng `int`** và nằm trong miền `byte` (-128..127), nên kiểu biểu thức `within` là `byte`.
- `1000` nằm ngoài miền `byte`, nên biểu thức `outside` dùng kiểu `int`.

Kiểm tra bằng overload:

~~~java
static String kind(byte value) { return "byte"; }
static String kind(int value) { return "int"; }

System.out.println(kind(flag ? small : 100));  // byte
System.out.println(kind(flag ? small : 1000)); // int
~~~

**Không nhầm literal với biến:** ngay cả khi một biến `int` đang chứa 100, biểu thức `flag ? small : intVariable` thông thường có kiểu `int`, vì giá trị của biến không trở thành *constant expression* chỉ nhờ nó đang bằng 100.

~~~java
int intVariable = 100;
System.out.println(kind(flag ? small : intVariable)); // int
~~~

Chi tiết này chứng tỏ việc chọn kiểu là **quy tắc compile time**, không phụ thuộc giá trị nhánh được chọn ở runtime.

## 6. Chuyển số nguyên lớn sang số thực có thể mất độ chính xác

~~~java
long exact = 9_007_199_254_740_993L; // 2^53 + 1
boolean flag = true;

double result = flag ? exact : 0.5;
System.out.println(result); // 9.007199254740992E15
~~~

Cả biểu thức điều kiện ở đây có kiểu `double`. Khi nhánh `long` được chọn, `exact` phải được chuyển sang `double`; số nguyên **2^53 + 1** không biểu diễn chính xác trong binary64 nên được làm tròn thành **2^53**.

**Hệ quả:** dù nhánh `0.5` không chạy, kiểu `double` của nó vẫn dẫn tới việc chuyển số nguyên lớn ở nhánh true. Nếu phải bảo toàn một ID/`long` chính xác, đừng trộn nó với số thực chỉ để tạo một biểu thức `?:`.

### Chuyển kiểu không sửa phép tính đã diễn ra trong nhánh

~~~java
boolean flag = true;
double quotient = flag ? (3 / 2) : 2.5;

System.out.println(quotient); // 1.0
~~~

`3 / 2` **đã thực hiện chia nguyên**, trả 1, rồi mới được chuyển sang `double` của toàn biểu thức. Nó **không trở thành phép chia 1.5** chỉ vì nhánh kia là `double`.

Nếu cần phần lẻ, chuyển kiểu **trước phép chia**:

~~~java
double quotient = flag ? (3.0 / 2) : 2.5;
System.out.println(quotient); // 1.5
~~~

## 7. Numeric wrapper: unboxing có thể xảy ra

Ví dụ quan trọng với `Integer` và `int`:

~~~java
Integer boxed = 7;
int primitive = 9;
boolean flag = true;

int selected = flag ? boxed : primitive;
System.out.println(selected); // 7
~~~

Trong cặp kiểu này, biểu thức điều kiện số cho kiểu `int`; khi nhánh `boxed` được chọn, Java **unbox `Integer`** để lấy giá trị nguyên thủy.

Nếu wrapper đang null:

~~~java
Integer missing = null;
// int result = true ? missing : 9;
// Khi chạy: NullPointerException do unbox missing.
~~~

Một điều rất quan trọng: **chỉ nhánh được chọn mới được đánh giá và chuyển kiểu cần thiết tại runtime**. Trong ví dụ sau nhánh wrapper null không được chọn nên không có lỗi:

~~~java
Integer missing = null;
int safe = true ? 9 : missing;
System.out.println(safe); // 9
~~~

Đừng nghĩ rằng nhánh null sẽ luôn ném NPE chỉ vì compiler biết nhánh đó có thể cần unboxing. Nó cần thực sự được chọn và dùng ở runtime.

## 8. Hai numeric wrapper khác nhau cũng có thể tạo kiểu nguyên thủy

~~~java
Integer whole = 7;
Double fraction = 2.5;
boolean flag = true;

Number chosen = flag ? whole : fraction;
System.out.println(chosen); // 7.0
~~~

Với cặp `Integer` và `Double`, đây là **numeric conditional**, Java áp dụng unboxing và quy tắc numeric promotion để có kiểu `double`. Khi gán cho `Number`, kết quả có thể được **boxing thành `Double`**. Không nên đoán rằng chọn `whole` thì object kết quả chắc chắn là `Integer`.

Nếu cần giữ nguyên loại object cụ thể theo nhánh, hãy thiết kế rõ **kiểu tham chiếu** và cách chuyển đổi thay vì dựa vào suy đoán của phép `?:`. Trong một số trường hợp, tách `if/else` thành gán `Number` rõ ràng sẽ dễ kiểm thử hơn.

Đây là một trong những lý do không nên viết các biểu thức `?:` trộn nhiều kiểu wrapper khi ngữ nghĩa về loại object quan trọng.

## 9. Biểu thức điều kiện boolean và `Boolean` nullable

~~~java
boolean flag = true;
boolean selected = flag ? true : false;
System.out.println(selected); // true
~~~

Một biểu thức có hai nhánh `boolean` có kiểu `boolean`; nếu phối hợp với `Boolean`, có thể phát sinh unboxing.

~~~java
Boolean boxed = null;
boolean flag = true;

// boolean result = flag ? boxed : false;
// Nếu nhánh boxed được chọn sẽ ném NullPointerException.
~~~

Ngoài ra, **chính điều kiện** cũng có thể là `Boolean`:

~~~java
Boolean condition = null;
// int value = condition ? 1 : 2;
// NullPointerException khi unbox condition để quyết định nhánh.
~~~

**Phân biệt lỗi:**
- Điều kiện null → lỗi khi **xác định nhánh**.
- Nhánh wrapper null → lỗi khi **nhánh được chọn cần unbox**.
- Nhánh không được chọn → không bị đánh giá, không tự ném NPE.

Nếu dữ liệu `Boolean` nullable, nên định nghĩa chính sách `null` rõ ràng, ví dụ dùng `Boolean.TRUE.equals(condition)` khi chỉ giá trị true mới được chấp nhận.

## 10. Biểu thức tham chiếu và target typing

Không phải `?:` nào cũng dùng numeric promotion. Khi hai nhánh thuộc nhóm tham chiếu, Java có thể dùng **kiểu mục tiêu** (*target type*) trong ngữ cảnh gán hoặc truyền đối số.

~~~java
boolean flag = true;

String label = flag ? "ready" : null;
System.out.println(label); // ready
~~~

Ví dụ rõ hơn với kiểu tổng quát:

~~~java
java.util.List<String> names = flag
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();

names.add("Java");
System.out.println(names.get(0)); // Java
~~~

Hai nhánh tham chiếu được kiểm tra theo **kiểu mục tiêu `List<String>`**; các toán tử `new ...<>()` cũng nhận ngữ cảnh kiểu phù hợp. Java không cần một “phép cộng kiểu” số học ở đây.

Với nhánh kiểu tham chiếu khác nhau:

~~~java
Object result = flag ? "ready" : Integer.valueOf(7);
System.out.println(result.getClass().getSimpleName()); // String
~~~

Đây là **reference conditional expression** và có target type `Object`. Chỉ nhánh được chọn tạo ra giá trị runtime, nhưng cả hai nhánh phải chuyển đổi được trong ngữ cảnh đích.

**Cẩn thận với `var`:** khi khởi tạo biến bằng `var x = flag ? expr1 : expr2;`, không có kiểu biến khai báo sẵn làm target type cho biểu thức con theo cách của ví dụ `List<String>` ở trên. Compiler phải xác định kiểu ở ngữ cảnh standalone; với các nhánh reference khác nhau có thể suy ra kiểu chung hoặc intersection type phức tạp. Nếu kiểu API cần chính xác và dễ đọc, **khai báo kiểu đích tường minh**.

## 11. `null` không có nghĩa mọi biểu thức `?:` đều nullable

Với reference:

~~~java
String text = true ? null : "backup";
System.out.println(text == null); // true
~~~

Nhánh true là null; kiểu kết quả vẫn có thể phù hợp `String` nhờ ngữ cảnh tham chiếu.

Nhưng với numeric conditional dùng primitive và wrapper:

~~~java
Integer nullable = null;
// int result = true ? nullable : 5;
~~~

Đây là trường hợp cần unboxing `nullable`, nên **không giống** reference conditional trả null bình thường. Không nên suy luận “một nhánh null thì toán tử sẽ trả null mà không lỗi” trước khi xác định **loại conditional expression**.

**Hợp đồng API:** nếu null là một trạng thái hợp lệ, thiết kế rõ output tham chiếu/Optional; nếu không chấp nhận null, validate trước khi dùng.

## 12. Thứ tự ưu tiên, tính kết hợp và điều kiện lồng nhau

Toán tử `?:` có tính kết hợp **từ phải sang trái**:

~~~java
int score = 75;
String grade = score >= 90 ? "A"
        : score >= 70 ? "B"
        : "C";

System.out.println(grade); // B
~~~

Được hiểu theo nhóm:

~~~java
String grade = score >= 90
        ? "A"
        : (score >= 70 ? "B" : "C");
~~~

Nếu biểu thức lồng nhiều nhánh có kiểu hỗn hợp, cả việc **chọn kiểu** và **thứ tự chọn nhánh** đều khó theo dõi. Ưu tiên `if/else if/else` khi có nhiều điều kiện, kiểm tra lỗi hoặc logic nghiệp vụ dài.

Dấu ngoặc giúp làm rõ cách nhóm, **nhưng không làm mọi cặp kiểu nhánh tự nhiên tương thích**, và không đổi quy tắc numeric promotion.

## 13. Khi nào nên dùng `if/else` thay vì `?:`?

Dùng `?:` khi hai nhánh là **hai giá trị ngắn, dễ đoán kiểu**:

~~~java
String status = active ? "ON" : "OFF";
int timeout = strict ? 100 : 300;
~~~

Cân nhắc `if/else` khi:
- Một nhánh có side effect, gọi nhiều method hoặc có thể ném lỗi.
- Hai nhánh chứa kiểu số/wrapper khác nhau cần chuyển đổi có chủ đích.
- Cần xử lý null, overflow, mất độ chính xác hoặc chính sách rounding.
- Có nhiều nhánh `?:` lồng nhau khó review.

Ví dụ làm rõ chuyển đổi:

~~~java
Number selected;
if (flag) {
    selected = whole;    // Giữ giá trị tham chiếu Integer
} else {
    selected = fraction; // Giữ giá trị tham chiếu Double
}
~~~

Cách này khác về **loại object được giữ** với numeric conditional `flag ? whole : fraction` trong một số tình huống. Lựa chọn đúng phụ thuộc hợp đồng mong muốn.

## 14. Bảng lỗi phổ biến

| Nhầm lẫn | Thực tế trong Java | Cách xử lý |
|---|---|---|
| `?:` luôn có kiểu của nhánh đang chạy | Kiểu được xác định theo quy tắc compile time | Xét cả hai nhánh và target type |
| `true ? 10 : 2.5` có kiểu int | Có kiểu `double` | Dùng numeric promotion đúng |
| `double d = flag ? 1 : 2;` làm `?:` thành double | Conditional số bên trong là int, rồi gán mới widening | Tách kiểu biểu thức và kiểu biến nhận |
| `byte b; flag ? b : 100` chắc chắn kiểu int | Hằng int 100 vừa byte → kết quả byte | Biết ngoại lệ constant-expression |
| `flag ? b : intVar` kiểu byte khi intVar đang bằng 100 | intVar thường không phải hằng compile time | Kiểu thường là int |
| Nhánh `long` luôn giữ chính xác khi nhánh kia double | Widening long→double có thể làm tròn | Giữ cùng loại số nếu cần chính xác |
| `flag ? (3/2) : 2.5` cho 1.5 | Chia nguyên 3/2 đã cho 1 | Dùng 3.0/2 trước |
| Wrapper null luôn an toàn vì có nhánh khác | Nhánh được chọn có thể unbox null | Guard null hoặc thiết kế reference output |
| Nhánh không được chọn vẫn chạy để chuyển kiểu | Chỉ nhánh được chọn được đánh giá runtime | Tách compile-time typing và runtime evaluation |
| `Boolean` null dùng làm condition nghĩa là false | Unboxing null ném NPE | Dùng chính sách null rõ |
| `Integer`/ `Double` chọn nhánh nào giữ đúng wrapper đó | Numeric conditional có thể unbox/promote rồi box lại | Nếu cần object identity, dùng if/else reference |
| `var` luôn suy kiểu như target khai báo tường minh | Không có kiểu đích khai báo sẵn như `List<String>` | Khai báo type khi quan trọng |
| `?:` lồng dài luôn dễ hơn if/else | Khó suy kiểu và thứ tự chọn nhánh | Tách if/else hoặc hàm rõ ý |

## 15. Chương trình Java 17 hoàn chỉnh

Tạo file đúng tên **`ConditionalExpressionTypeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public final class ConditionalExpressionTypeDemo {
    private ConditionalExpressionTypeDemo() {}

    static String kind(byte value) { return "byte"; }
    static String kind(int value) { return "int"; }
    static String kind(long value) { return "long"; }
    static String kind(float value) { return "float"; }
    static String kind(double value) { return "double"; }

    static int trace(String label, int value) {
        System.out.println("evaluated " + label);
        return value;
    }

    public static void main(String[] args) {
        boolean choose = true;

        System.out.println("numeric int="
                + kind(choose ? 10 : 20));
        System.out.println("numeric long="
                + kind(choose ? 10 : 20L));
        System.out.println("numeric float="
                + kind(choose ? 10 : 2.5f));
        System.out.println("numeric double="
                + kind(choose ? 10 : 2.5));

        byte small = 10;
        int regularInt = 100;
        System.out.println("byte constant="
                + kind(choose ? small : 100));
        System.out.println("byte too large="
                + kind(choose ? small : 1000));
        System.out.println("byte int variable="
                + kind(choose ? small : regularInt));

        double widenedTarget = choose ? 1 : 2;
        System.out.println("widened assignment=" + widenedTarget);

        long exact = 9_007_199_254_740_993L;
        double rounded = choose ? exact : 0.5;
        System.out.println("long promoted to double=" + rounded);

        double lateDivision = choose ? (3 / 2) : 2.5;
        double earlyDivision = choose ? (3.0 / 2) : 2.5;
        System.out.println("integer division then widen=" + lateDivision);
        System.out.println("floating division=" + earlyDivision);

        int selected = choose
                ? trace("true", 7)
                : trace("false", 9);
        System.out.println("selected=" + selected);

        Integer boxed = 7;
        int primitive = 9;
        System.out.println("int unboxed=" + (choose ? boxed : primitive));

        Integer missing = null;
        int safe = choose ? 9 : missing;
        System.out.println("unselected null=" + safe);
        try {
            int broken = choose ? missing : 9;
            System.out.println(broken);
        } catch (NullPointerException ex) {
            System.out.println("selected null=NullPointerException");
        }

        Integer whole = 7;
        Double fraction = 2.5;
        Number numericWrapper = choose ? whole : fraction;
        System.out.println("wrapper value=" + numericWrapper);
        System.out.println("wrapper class="
                + numericWrapper.getClass().getSimpleName());

        Number referenceWrapper;
        if (choose) {
            referenceWrapper = whole;
        } else {
            referenceWrapper = fraction;
        }
        System.out.println("reference class="
                + referenceWrapper.getClass().getSimpleName());

        Boolean boxedCondition = null;
        try {
            int number = boxedCondition ? 1 : 2;
            System.out.println(number);
        } catch (NullPointerException ex) {
            System.out.println("null condition=NullPointerException");
        }

        String text = choose ? "ready" : null;
        System.out.println("reference string=" + text);
        String nullable = choose ? null : "fallback";
        System.out.println("reference null=" + (nullable == null));

        Object objectValue = choose ? "ready" : Integer.valueOf(7);
        System.out.println("target object class="
                + objectValue.getClass().getSimpleName());

        List<String> list = choose
                ? new ArrayList<>()
                : new LinkedList<>();
        list.add("Java");
        System.out.println("target typed list=" + list.get(0));

        int score = 75;
        String grade = score >= 90 ? "A"
                : score >= 70 ? "B"
                : "C";
        System.out.println("nested condition=" + grade);
    }
}
~~~

**Bash (Linux/macOS)** — terminal đang ở thư mục chứa file, yêu cầu JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ConditionalExpressionTypeDemo.java
java -cp . ConditionalExpressionTypeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ConditionalExpressionTypeDemo.java
java -cp . ConditionalExpressionTypeDemo
~~~

Không dùng Maven, Gradle hoặc thư viện ngoài JDK.

### Exact expected stdout

~~~text
numeric int=int
numeric long=long
numeric float=float
numeric double=double
byte constant=byte
byte too large=int
byte int variable=int
widened assignment=1.0
long promoted to double=9.007199254740992E15
integer division then widen=1.0
floating division=1.5
evaluated true
selected=7
int unboxed=7
unselected null=9
selected null=NullPointerException
wrapper value=7.0
wrapper class=Double
reference class=Integer
null condition=NullPointerException
reference string=ready
reference null=true
target object class=String
target typed list=Java
nested condition=B
~~~

**Giải thích điểm quan trọng của stdout:**

1. Bốn dòng `numeric ...` xác nhận numeric conditional expression có kiểu chung do Java quyết định.
2. `byte constant=byte`, `byte too large=int`: hằng `int` vừa miền có quy tắc riêng; một biến `int` thường không được hưởng điều kiện này.
3. `widened assignment=1.0`: toán tử `?:` bên trong có kiểu int; widening diễn ra ở phép gán ra biến double.
4. `long promoted to double`: `long` lớn bị làm tròn khi chọn biểu thức có kiểu `double`.
5. `integer division then widen=1.0`: chuyển kiểu ở ngoài không làm phép chia nguyên thành phép chia thực.
6. Không có `evaluated false`: Java chỉ thực hiện nhánh true.
7. `selected null` ném NPE do unboxing nhánh được chọn; `unselected null=9` không có lỗi.
8. `wrapper class=Double` đối lập `reference class=Integer`: numeric conditional khác việc gán trực tiếp từng wrapper vào `Number`.
9. `null condition` ném NPE ở bước đánh giá điều kiện `Boolean`.
10. `target typed list=Java` chứng minh biểu thức tham chiếu có thể dùng kiểu đích `List<String>`; `nested condition=B` do toán tử `?:` kết hợp phải.

## 16. Bài tập có đáp án

### Bài A — xác định kiểu biểu thức

~~~java
boolean flag = true;
var result = flag ? 3 : 4L;
System.out.println(result);
~~~

**Đáp án:** `result` có kiểu **`long`**, stdout là `3`. `var` không làm biểu thức thành kiểu runtime động.

### Bài B — hằng `int` với `byte`

~~~java
byte b = 5;
System.out.println(kind(true ? b : 100));
System.out.println(kind(true ? b : 200));
~~~

**Đáp án:**

~~~text
byte
int
~~~

Hàm overload `kind` định nghĩa trong chương trình đầy đủ. 100 nằm trong miền byte, 200 không nằm trong miền byte.

### Bài C — unboxing nhánh null

~~~java
Integer missing = null;
int value = true ? 1 : missing;
System.out.println(value);
~~~

**Đáp án:** `1`, không NPE vì nhánh `missing` không được chọn. Nếu đổi `true` thành `false`, nhánh `Integer` null được chọn và cần unboxing → `NullPointerException`.

### Bài D — chia nguyên hay chia thực?

~~~java
boolean flag = true;
double result = flag ? (7 / 2) : 2.5;
System.out.println(result);
~~~

**Đáp án:** `3.0`. `7 / 2` xảy ra trong nhánh với kiểu nguyên, cắt phần lẻ trước khi chuyển sang double.

### Bài E — chọn object hay chọn giá trị số?

~~~java
Integer a = 7;
Double b = 2.5;
Number result = true ? a : b;
System.out.println(result.getClass().getSimpleName());
~~~

**Đáp án:** `Double`. Numeric conditional thực hiện unboxing/numeric promotion rồi boxing khi gán vào Number, chứ không bảo toàn wrapper Integer chỉ vì nhánh true chọn a.

### Bài F — target typing với reference

~~~java
java.util.List<String> names = true
        ? new java.util.ArrayList<>()
        : new java.util.LinkedList<>();
names.add("JDK 17");
System.out.println(names.get(0));
~~~

**Đáp án:** `JDK 17`. Biểu thức tham chiếu nhận target type `List<String>`, cho phép hai nhánh được kiểm tra trong ngữ cảnh đó.

## 17. Checklist và kết luận

- [ ] Hiểu cú pháp `condition ? whenTrue : whenFalse`.
- [ ] Biết chỉ **một nhánh được chọn** được đánh giá runtime.
- [ ] Hiểu compiler xét cả hai nhánh để kiểm tra kiểu.
- [ ] Phân biệt boolean, numeric và reference conditional expression.
- [ ] Biết numeric promotion khi trộn `int`, `long`, `float`, `double`.
- [ ] Biết quy tắc đặc biệt với `byte`/`short` và hằng `int` vừa miền.
- [ ] Phân biệt kiểu của `?:` với chuyển kiểu ở phép gán ra biến.
- [ ] Hiểu `long → double` có thể mất độ chính xác; chuyển kiểu ngoài không sửa phép chia nguyên đã tính.
- [ ] Nhận diện unboxing và NPE ở nhánh wrapper được chọn.
- [ ] Biết `Boolean` null khi dùng làm điều kiện có thể NPE.
- [ ] Hiểu reference conditional có thể chịu target typing, `var` không thay thế khai báo kiểu khi cần rõ API.
- [ ] Hiểu tính kết hợp phải của `?:` và tránh lồng điều kiện quá sâu.
- [ ] Biên dịch `ConditionalExpressionTypeDemo.java` trên Java 17+ và đối chiếu exact stdout.

**Kết luận:** Toán tử ba ngôi `?:` trong Java 17+ không đơn giản là “trả nguyên kiểu của nhánh được chọn”. Kiểu được quyết định **ở compile time**, đôi khi dựa vào **kiểu mục tiêu**, trong khi runtime chỉ đánh giá **nhánh được chọn**. Numeric promotion, narrowing đặc biệt và boxing/unboxing có thể làm kết quả khác trực giác hoặc phát sinh lỗi. Hãy dùng `?:` cho lựa chọn giá trị ngắn, cùng kiểu rõ ràng; khi có nhiều kiểu hỗn hợp hoặc chính sách chuyển đổi quan trọng, ưu tiên `if/else` và chuyển kiểu tường minh.