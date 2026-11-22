# Kiểm tra kiểu và gán ý nghĩa cho biểu thức trong quá trình biên dịch Java

Khi đọc biểu thức Java như `small + 1`, `list.get(0)`, `choose(null)` hoặc `text -> text.length()`, ta có thể đoán nó sẽ làm gì. Nhưng để phát sinh bytecode, trình biên dịch **phải xác định tên nào chỉ đối tượng nào, mỗi biểu thức có kiểu gì, toán tử/phương thức nào được chọn, và các phép chuyển đổi nào được phép**. Quá trình đó thường được gọi là *semantic analysis*, *name/type resolution*, *type checking* và *attribution* (gán kiểu/ngữ nghĩa cho nút trong cây cú pháp).

Bài học đặt trong ngữ cảnh **các giai đoạn của `javac`**, dùng Java 17 trở lên. Trọng tâm là giải thích được vì sao một biểu thức hợp lệ hoặc bị từ chối **trước khi chương trình chạy**, và từ thông báo lỗi biên dịch có thể suy ra bước kiểm tra đang thất bại.

## 1. Từ cú pháp hợp lệ đến biểu thức có ý nghĩa

Xét ba đoạn:

~~~java
int sum = 1 + 2;
int sum2 = "1" + 2;
int sum3 = "1" - 2; // lỗi kiểu/toán tử: '-' không áp dụng cho String và int
~~~

Cả ba đều có dạng cú pháp phù hợp với một phép toán nhị phân, nhưng chỉ hai biểu thức đầu hợp lệ về ngữ nghĩa Java.

- `1 + 2`: hai toán hạng `int`, phép `+` là cộng số nguyên; kết quả có kiểu `int`.
- `"1" + 2`: khi có toán hạng `String`, phép `+` thực hiện **nối chuỗi**; kết quả là `String` có giá trị `"12"`.
- `"1" - 2`: toán tử `-` yêu cầu toán hạng kiểu số thích hợp; không có phép trừ `String` trong ngôn ngữ Java. Compiler từ chối trước khi sinh bytecode.

**Parser** xác định biểu thức được tổ chức thành những nút nào trong cây cú pháp trừu tượng (*AST*). **Kiểm tra ngữ nghĩa** xem các nút đó nói đến kiểu, biến, phương thức và phép toán nào, và chúng có hợp lệ theo quy tắc ngôn ngữ hay không. Một AST hợp lệ về cú pháp chưa đủ để chương trình được chấp nhận.

### 1.1. Vị trí trong pipeline javac

Sơ đồ dưới đây là **mô hình khái niệm**, không cam kết rằng mọi thao tác nội bộ của mọi phiên bản `javac` xảy ra thành các pha tách biệt tuyệt đối:

~~~text
Tệp .java
    |
    v
Đọc ký tự, phân tích từ vựng và cú pháp
    |
    v
AST: các khai báo và biểu thức có cấu trúc
    |
    v
Enter / xây dựng thông tin ký hiệu và phạm vi
    |
    v
Resolve + Attr + Check: phân giải tên, gán kiểu,
kiểm tra biểu thức, phương thức, phép chuyển đổi
    |
    v
Flow: kiểm tra luồng dữ liệu/điều kiện dùng biến
    |
    v
Các bước chuyển đổi biểu diễn và phát sinh bytecode
    |
    v
Các tệp .class
~~~

Trong mã nguồn OpenJDK của `javac`, những tên như `Enter`, `Resolve`, `Attr`, `Check` và `Flow` tương ứng với các trách nhiệm liên quan; một phép kiểm tra cụ thể có thể cần thông tin do nhiều bộ phận phối hợp. Đừng hiểu sơ đồ như thứ tự bắt buộc của mọi lời gọi nội bộ.

- **Enter** ghi nhận các khai báo kiểu, thành viên và thông tin ký hiệu cần cho phân tích.
- **Resolve** tra cứu và chọn nghĩa cho tên, thành viên hoặc lời gọi khi có nhiều ứng viên.
- **Attr (attribution)** gắn thông tin kiểu/ngữ nghĩa cho các cấu trúc của AST dựa trên ngữ cảnh.
- **Check** kiểm tra các ràng buộc như chuyển đổi kiểu, khả năng truy cập và tính hợp lệ của cấu trúc.
- **Flow** kiểm tra các tính chất liên quan đến luồng điều khiển/dữ liệu như *definite assignment*, tính có thể đến được và các quy tắc liên quan.

Kết quả gán nghĩa là compiler biết biểu thức `account.balance()` đề cập đến phương thức nào và có kiểu trả về gì. Những thông tin này tiếp tục được dùng trong quá trình biên dịch.

## 2. Phân giải tên và tra cứu ký hiệu trước khi gán kiểu

Tên `value` có thể chỉ biến cục bộ, tham số, trường hoặc thành viên của kiểu khác. Compiler dựa vào **phạm vi (scope)**, khai báo và quy tắc shadowing để tìm biểu tượng tương ứng.

~~~java
public class ScopeExample {
    private int value = 100;

    void print(int value) {
        int doubled = value * 2;
        System.out.println(doubled);   // tham số value: int
        System.out.println(this.value); // trường value: int
    }
}
~~~

Đây là một lớp Java hợp lệ, nhưng không có `main` nên không tự chạy như chương trình độc lập. Trong `print`, tên đơn `value` được phân giải thành **tham số**, còn `this.value` chỉ trường của đối tượng. Cả hai có kiểu `int` nhưng là hai ký hiệu khác nhau; attribution không chỉ đọc chữ `int`, nó còn xác định **đúng khai báo**.

Một quá trình tra cứu tên có thể xem xét:

1. Phạm vi biến cục bộ, tham số, kiểu và khai báo liên quan.
2. Thành viên của lớp hiện tại, lớp cha, interface và các kiểu có liên quan theo quy tắc Java.
3. Các kiểu được nhập bằng `import`, tên đầy đủ của package và quy tắc phân giải tên.
4. Khả năng truy cập của khai báo sau khi tìm thấy, chẳng hạn `private`, package-private hoặc `public`.

`import` không cấp quyền truy cập và không tự đưa JAR lên classpath. Nếu tên được viết đúng nhưng compiler không có khai báo kiểu trên đường dẫn tìm lớp/nguồn, bước phân giải tên vẫn thất bại. Thông báo `cannot find symbol` thường hướng đến lỗi này.

Cần phân biệt **shadowing** (một khai báo cùng tên che khai báo khác theo phạm vi) với **overloading** (nhiều phương thức cùng tên nhưng chữ ký tham số khác nhau). Phân giải một tên biến và chọn một lời gọi overload có các quy tắc khác nhau.

## 3. Kiểu của biểu thức và ngữ cảnh mong đợi

Java là ngôn ngữ được kiểm tra kiểu tĩnh. Compiler biết kiểu của biến hoặc suy luận nó từ khai báo/biểu thức liên quan. Mỗi biểu thức được kiểm tra xem có thể xuất hiện trong ngữ cảnh đó không.

~~~java
int count = 10;
long total = count;      // widening primitive: int -> long
Integer boxed = count;   // boxing: int -> Integer
int again = boxed;       // unboxing: Integer -> int
// int invalid = "10";   // lỗi: String không chuyển ngầm thành int
~~~

Các phép gán được compiler kiểm tra theo quy tắc *assignment conversion*. Chúng không đồng nhất với mọi phép chuyển đổi có thể viết bằng cast. Ví dụ `long` sang `int` thường yêu cầu ép kiểu tường minh vì có thể mất dữ liệu:

~~~java
long large = 3_000_000_000L;
int truncated = (int) large; // có thể mất thông tin
~~~

Compiler chấp nhận cú pháp cast hợp lệ nhưng **không bảo đảm** giá trị số được giữ nguyên. Với cast tham chiếu, compiler kiểm tra quan hệ kiểu cho phép cast; việc đối tượng thực tế có đúng kiểu lúc chạy còn có thể gây `ClassCastException`. Biên dịch đúng không có nghĩa mọi đường đi lúc chạy đều an toàn.

### 3.1. Kiểu nguyên thủy, tham chiếu và null

`int`, `long`, `double`, `boolean`, ... là primitive types; `String`, `List<String>`, `Integer`, array và các class/interface khác là reference types. Literal `null` có kiểu null đặc biệt và có thể gán cho các kiểu tham chiếu phù hợp, nhưng không gán trực tiếp cho `int`.

~~~java
String text = null;        // hợp lệ
Integer boxed = null;      // hợp lệ
// int number = null;      // lỗi biên dịch
int value = boxed;         // biên dịch được, nhưng NPE lúc chạy vì unboxing null
~~~

Hãy tách rõ hai câu hỏi: **biểu thức có kiểu phù hợp để biên dịch không?** và **dữ liệu thực tế có gây lỗi khi chạy không?** Kiểm tra kiểu tĩnh không thay thế các kiểm tra null hoặc kiểm tra điều kiện runtime.

### 3.2. Kiểu của toán tử số

Trong biểu thức số, Java sử dụng các quy tắc *unary/binary numeric promotion*. Với phép `+` số học, `byte`, `short` và `char` thường được nâng lên `int`; kết quả không tự giữ kiểu nhỏ:

~~~java
byte a = 7;
int sum = a + 1;     // biểu thức a + 1 có kiểu int
// byte bad = a + 1; // lỗi: cần chuyển int -> byte
byte known = 1 + 2;  // hợp lệ vì đây là hằng int có giá trị nằm trong byte
~~~

Trường hợp cuối thể hiện **narrowing của hằng biểu thức** được cho phép trong một số ngữ cảnh gán/khởi tạo. Quy tắc cho hằng compile-time khác với một biểu thức bất kỳ có cùng giá trị khi chạy. Nếu viết `byte known = 128;` thì compiler từ chối vì giá trị vượt phạm vi `byte`.

Tương tự:

~~~java
double result = 5 / 2;    // phần 5 / 2 là phép chia int; result = 2.0
double fraction = 5 / 2.0; // phép chia double; fraction = 2.5
~~~

Compiler đã quyết định phép chia áp dụng trên kiểu nào trước khi xét phép gán cuối cùng vào `double`.

## 4. Xác định phương thức được gọi: overload resolution

Khi gặp `choose(small)`, compiler phải tìm các phương thức tên `choose` có thể truy cập và **phù hợp với kiểu đối số**. Đây là bước phân giải lời gọi, không phải chọn ngẫu nhiên lúc chạy theo “kiểu gần nhất”.

Quy tắc chọn overload Java dùng nhiều giai đoạn áp dụng, trong đó ưu tiên cách gọi phù hợp không cần boxing/varargs trước các giai đoạn lỏng hơn; sau đó xét phương thức **most specific**. Vì vậy các cách chuyển đổi primitive widening, boxing/unboxing và varargs không phải lúc nào cũng có cùng độ ưu tiên.

~~~java
static String choose(int value) {
    return "int";
}
static String choose(long value) {
    return "long";
}
static String choose(Integer value) {
    return "Integer";
}
~~~

Các phương thức trên là **đoạn trích đặt bên trong một lớp**; chương trình đầy đủ ở phần 8. Với `byte small = 7;`:

| Lời gọi | Đối số được xét ở compile-time | Overload được chọn |
|---|---|---|
| `choose(small)` | `byte`; có thể widening thành `int` | `choose(int)` |
| `choose(7L)` | Literal `long` | `choose(long)` |
| `choose(Integer.valueOf(7))` | `Integer` | `choose(Integer)` |

Không dựa vào giá trị số 7 để chọn overload; compiler dựa vào **kiểu tĩnh của biểu thức**.

### 4.1. null và lời gọi mơ hồ

Nếu một class có hai overload:

~~~java
static void accept(String value) { }
static void accept(Integer value) { }
~~~

thì lời gọi `accept(null)` **không hợp lệ**: `null` có thể chuyển thành cả `String` lẫn `Integer`, nhưng hai kiểu này không có quan hệ kiểu phụ nào khiến một phương thức được xem là cụ thể hơn theo cách cần thiết. `javac` báo `reference to accept is ambiguous`.

Ngược lại:

~~~java
static String label(Object value) { return "Object"; }
static String label(String value) { return "String"; }
~~~

Lời gọi `label(null)` hợp lệ và chọn `label(String)` vì `String` là subtype của `Object`, nên trong tình huống này overload `String` cụ thể hơn.

**Overloading** được lựa chọn bằng kiểu compile-time. **Overriding** có thể dùng dynamic dispatch lúc chạy: sau khi compiler chọn chữ ký phương thức instance, JVM quyết định implementation override tương ứng đối tượng thực tế. Không nên nhập hai cơ chế này làm một.

### 4.2. Static type quyết định overload

~~~java
Object item = "Java";
// label(item) chọn label(Object), dù đối tượng runtime là String.
~~~

Nếu cả `label(Object)` và `label(String)` tồn tại, compiler sẽ chọn `label(Object)` vì **biến `item` có kiểu tĩnh `Object`**. Muốn gọi overload `String` phải có thông tin kiểu phù hợp, ví dụ kiểm tra/cast hợp lệ. Cast sai kiểu có thể ném lỗi lúc chạy.

## 5. Kiểu do ngữ cảnh cung cấp: target typing và poly expressions

Không phải mọi biểu thức có một kiểu tự suy ra mà không cần nhìn bên ngoài. Một số biểu thức Java được kiểm tra theo **kiểu đích** (target type) từ nơi nó xuất hiện. Khái niệm *poly expression* quan trọng với lambda, method reference, lời gọi generic và một số biểu thức như conditional/switch trong ngữ cảnh thích hợp.

### 5.1. Lambda cần functional interface mục tiêu

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Vì kiểu đích là `Function<String, Integer>`, compiler biết tham số `text` có kiểu `String`. Nó kiểm tra lời gọi `text.length()` có kiểu `int`, rồi xét chuyển đổi boxing từ `int` sang `Integer` để phù hợp kết quả mong đợi. Compiler không cần chạy lambda để biết các kiểu này.

Ngược lại, đoạn sau không biên dịch:

~~~java
// var operation = text -> text.length();
~~~

Khi chỉ có `var` mà không có kiểu đích của functional interface, lambda không có đủ ngữ cảnh để xác định kiểu. Phải khai báo một functional interface phù hợp hoặc cung cấp lambda trong ngữ cảnh có target type, chẳng hạn làm đối số của một phương thức nhận `Function<String, Integer>`.

Method reference, chẳng hạn `String::length`, cũng cần kiểm tra khả năng tương thích với chữ ký functional interface trong ngữ cảnh cụ thể.

### 5.2. Suy luận kiểu generic và kiểu của lời gọi

~~~java
static <T> T identity(T value) {
    return value;
}

String text = identity("OK");
~~~

Compiler suy luận tham số kiểu `T` để lời gọi `identity("OK")` có thể phù hợp với đối số và ngữ cảnh gán. Kiểu trả về biểu thức được gán nghĩa thông qua các ràng buộc kiểu; không có việc Java thử chạy hàm để “quan sát” kiểu trả về.

Một số lời gọi phương thức generic là *poly expressions* trong ngữ cảnh assignment/invocation; kiểu đích có thể tham gia suy luận. Ví dụ:

~~~java
java.util.List<String> names = java.util.List.of("Lan", "Mai");
~~~

`List.of` là phương thức generic; compiler tìm type argument phù hợp. Danh sách có các phần tử `String`, nên `names.get(0)` có kiểu compile-time `String`.

Generic Java kiểm tra tại thời điểm biên dịch nhưng nhiều thông tin generic không tồn tại như một kiểu tham số hóa độc lập ở runtime do **type erasure**. Kiểu lúc compile-time và kiểu lớp runtime là hai tầng thông tin khác nhau.

### 5.3. var suy luận từ initializer

~~~java
var names = java.util.List.of("Lan", "Mai");
var first = names.get(0); // first có kiểu String
~~~

`var` là suy luận kiểu **biến cục bộ**, không phải kiểu động hay `Object` mặc định. Compiler phải suy ra một kiểu hợp lệ từ initializer. `var x = null;` không biên dịch do không có kiểu có thể suy ra theo quy tắc này; `var f = x -> x;` cũng không đủ target type cho lambda.

Cần chú ý `var list = new java.util.ArrayList<>();` không tự biết “sau này ta sẽ thêm String” vào danh sách; khi constructor diamond không có ngữ cảnh phần tử rõ ràng, suy luận có thể cho `ArrayList<Object>`. Hãy dùng kiểu khai báo rõ ràng khi đó là hợp đồng dữ liệu cần bảo đảm.

## 6. Tính tương thích kiểu trong generics, biểu thức điều kiện và switch

### 6.1. Generic invariance và wildcard

~~~java
java.util.List<Integer> integers = java.util.List.of(1, 2);
// java.util.List<Number> numbers = integers; // lỗi
java.util.List<? extends Number> readonlyNumbers = integers;
~~~

Dù `Integer` là subtype của `Number`, `List<Integer>` **không** là subtype của `List<Number>`. Nếu cho phép gán đó, một danh sách `Integer` có thể bị thêm `Double` qua biến `List<Number>`, phá ràng buộc phần tử. Wildcard `? extends Number` cho phép đọc các phần tử như `Number` nhưng hạn chế thêm phần tử khác `null` theo contract kiểu.

Compiler còn dùng các quy tắc *capture conversion* để xử lý wildcard trong nhiều biểu thức và lời gọi generic. Không phải mọi lỗi suy luận generic đều là “compiler không biết loại phần tử”; có thể là hệ ràng buộc thực sự mâu thuẫn.

### 6.2. Conditional expression

~~~java
int score = 10;
String category = score >= 8 ? "High" : "Low";
long count = true ? 1 : 2L;
~~~

Compiler xác định kiểu của điều kiện `score >= 8` là `boolean`, rồi kiểm tra hai nhánh của biểu thức `?:` theo các quy tắc riêng. Trong ví dụ thứ hai, nhánh kiểu `int` và `long` dẫn đến kết quả `long`. Với một số conditional expressions có kiểu tham chiếu, **target type** của phép gán cũng tham gia xác định tính hợp lệ.

Đừng luôn suy kiểu của `?:` bằng một luật giản đơn “lấy kiểu cha chung”: Java có bảng quy tắc riêng cho nhánh boolean/numeric/reference, hằng biểu thức và ngữ cảnh poly.

### 6.3. Switch expression

~~~java
int price = switch ("VIP") {
    case "VIP" -> 10;
    default -> 20;
};
~~~

Vì đây là **switch expression**, toàn bộ `switch` phải cung cấp giá trị hợp lệ, các nhánh được kiểm tra kiểu và phải có khả năng tạo ra kết quả theo các quy tắc của Java. `switch` statement truyền thống không đương nhiên có kiểu kết quả để gán vào biến. Ví dụ trên có kiểu phù hợp với `int` và trả về 10 khi chạy.

Tương tự lambda, một số switch expressions có thể được xét theo kiểu đích. Việc compile-time kiểm tra tính bao phủ các nhánh khác với runtime lựa chọn nhánh khi chạy.

## 7. Những kiểm tra ngữ nghĩa thường đi cùng type attribution

**Kiểu đúng** là điều kiện quan trọng nhưng chưa phải duy nhất để Java biên dịch thành công.

### 7.1. Definite assignment

~~~java
void show(boolean condition) {
    int number;
    if (condition) {
        number = 42;
    }
    // System.out.println(number); // lỗi: number có thể chưa được gán
}
~~~

Compiler phân tích luồng điều khiển để biết biến cục bộ đã được gán trên mọi đường đi đến điểm sử dụng hay chưa. Biến `number` có kiểu `int` xác định, nhưng thao tác đọc vẫn không hợp lệ khi có nhánh chưa gán giá trị.

### 7.2. Phạm vi biến trong pattern và lambda

~~~java
void printIfText(Object value) {
    if (value instanceof String s) {
        System.out.println(s.length());
    }
}
~~~

`s` chỉ có phạm vi ở những vị trí mà phân tích flow-scoping bảo đảm pattern `String s` đã khớp. Không thể dùng `s` một cách tùy tiện bên ngoài phạm vi được phép, dù khai báo đã xuất hiện trong mã nguồn.

Với lambda, biến cục bộ được capture phải là `final` hoặc *effectively final*:

~~~java
int offset = 2;
java.util.function.IntUnaryOperator plus = x -> x + offset;
// offset = 3; // nếu bỏ comment, offset không còn effectively final
~~~

Dù toán tử `+` có các kiểu toán hạng hợp lệ, compiler vẫn áp dụng quy tắc capture và tính bất biến hiệu dụng.

### 7.3. Quyền truy cập, checked exceptions và return type

Compiler cũng kiểm tra việc truy cập thành viên `private`, có thể yêu cầu `try/catch` hoặc `throws` cho checked exceptions, và kiểm tra các câu lệnh `return` tương thích kiểu khai báo. Lỗi `has private access`, `unreported exception` hay `incompatible types` phản ánh những ràng buộc ngữ nghĩa khác nhau; không nên xem chúng là lỗi cú pháp.

**Giới hạn của kiểm tra tĩnh:** các ngoại lệ như `NullPointerException`, `ClassCastException`, tràn số nguyên, truy cập dữ liệu không hợp lệ hoặc kết quả nghiệp vụ sai vẫn có thể xuất hiện khi chạy dù chương trình đã qua hết kiểm tra kiểu.

## 8. Chương trình Java 17 đầy đủ để quan sát kết quả gán kiểu

Tạo tệp **`TypeAttributionDemo.java`** với toàn bộ nội dung sau (không có dòng `package`, nên chạy tại thư mục chứa tệp). Chương trình minh họa chuyển đổi số, overload, nhận diện null, generic inference, target typing lambda và switch expression.

~~~java
import java.util.List;
import java.util.function.Function;

public final class TypeAttributionDemo {
    static String choose(int value) { return "int"; }
    static String choose(long value) { return "long"; }
    static String choose(Integer value) { return "Integer"; }

    static String label(Object value) { return "Object"; }
    static String label(String value) { return "String"; }

    static <T> T identity(T value) { return value; }

    public static void main(String[] args) {
        byte small = 7;
        int sum = small + 1;

        System.out.println(choose(small));
        System.out.println(choose(7L));
        System.out.println(choose(Integer.valueOf(7)));
        System.out.println(label(null));
        System.out.println(sum);

        List<String> names = List.of("Lan", "Mai");
        var first = names.get(0);
        System.out.println(first);

        Function<String, Integer> length = text -> text.length();
        System.out.println(length.apply("Java"));

        String text = identity("OK");
        System.out.println(text);

        int price = switch ("VIP") {
            case "VIP" -> 10;
            default -> 20;
        };
        System.out.println(price);
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn, trong thư mục chứa tệp:

~~~sh
javac --release 17 -encoding UTF-8 TypeAttributionDemo.java
java TypeAttributionDemo
~~~

**Stdout chính xác đã kiểm chứng bằng JDK chạy `javac --release 17`:**

~~~text
int
long
Integer
String
8
Lan
4
OK
10
~~~

Giải nghĩa từng nhóm:

| Kết quả | Quyết định lúc compile-time |
|---|---|
| `int` | `choose(byte)` không tồn tại; widening `byte → int` chọn `choose(int)` |
| `long` | Literal `7L` có kiểu `long`, chọn overload `long` |
| `Integer` | Đối số có kiểu `Integer`, chọn overload trùng khớp |
| `String` | `label(null)` chọn overload `String` cụ thể hơn `Object` |
| `8` | `small + 1` có kiểu `int` |
| `Lan` | `names.get(0)` có kiểu `String`; `var first` suy ra `String` |
| `4` | Lambda được target-type là `Function<String,Integer>`; `length()` trả `int` |
| `OK` | Generic `identity` suy luận kiểu phù hợp với `String` |
| `10` | Switch expression trả `int` từ nhánh `VIP` |

Các quyết định chọn overload, tính hợp lệ của toán tử, chuyển đổi kiểu và suy luận lambda/generic được xác định khi biên dịch. Giá trị thực tế của điều kiện, phần tử danh sách và việc thực thi lời gọi phương thức vẫn diễn ra tại runtime.

## 9. Hai lỗi compile-time có thể tái hiện

Các ví dụ dưới đây **cố ý không hợp lệ**. Lưu mỗi đoạn vào tệp riêng, không thêm vào `TypeAttributionDemo.java` nếu bạn muốn chương trình mẫu ở phần 8 vẫn chạy.

### 9.1. Không tương thích kiểu

Tệp `InvalidAssignment.java`:

~~~java
public class InvalidAssignment {
    int value = "42";
}
~~~

Chạy:

~~~sh
javac --release 17 -encoding UTF-8 InvalidAssignment.java
~~~

Kết quả là compiler từ chối, với phần lỗi tương ứng:

~~~text
error: incompatible types: String cannot be converted to int
~~~

Lý do: `"42"` là literal `String` dù nội dung trông giống con số. Java không tự phân tích chuỗi thành số trong phép gán; muốn chuyển đổi dữ liệu, phải gọi phương thức thích hợp như `Integer.parseInt("42")` và xử lý đầu vào không hợp lệ.

### 9.2. Overload mơ hồ

Tệp `Ambiguous.java`:

~~~java
public class Ambiguous {
    static void accept(String value) {}
    static void accept(Integer value) {}

    public static void main(String[] args) {
        accept(null);
    }
}
~~~

Chạy:

~~~sh
javac --release 17 -encoding UTF-8 Ambiguous.java
~~~

Compiler từ chối lời gọi, với phần lỗi:

~~~text
error: reference to accept is ambiguous
~~~

Cả hai phương thức đều nhận được `null` nhưng không overload nào được xác định là cụ thể hơn. Có thể xác định lựa chọn bằng cast thích hợp, ví dụ `accept((String) null)`, nếu đó thực sự là ý định của người viết. Dòng lỗi và cách căn chỉnh dấu `^` có thể khác theo phiên bản/compiler flags; bản chất lỗi là **không phân giải được lời gọi đến một phương thức duy nhất**.

## 10. Đọc thông báo lỗi theo lớp nguyên nhân

Một lỗi từ `javac` thường chứa vị trí file/dòng, tên lỗi và ngữ cảnh kỳ vọng. Có thể phân loại ban đầu:

| Thông báo/triệu chứng | Nguyên nhân ngữ nghĩa hay gặp | Câu hỏi cần kiểm tra |
|---|---|---|
| `cannot find symbol` | Tên không phân giải được | Tên có khai báo, đúng scope/package/classpath không? |
| `package ... does not exist` | Không tìm được khai báo từ package | Source path, classpath/module path có đúng không? |
| `incompatible types` | Biểu thức không thể chuyển thành kiểu yêu cầu | Kiểu nguồn, kiểu đích và conversion được phép là gì? |
| `no suitable method found` | Không overload nào áp dụng được | Đối số có kiểu nào; có cần chuyển đổi hợp lệ không? |
| `reference to ... is ambiguous` | Có nhiều overload hợp lệ, không chọn duy nhất | Các overload cạnh tranh có quan hệ specific nào không? |
| `bad operand types for binary operator` | Toán tử không được phép trên các kiểu toán hạng | Kiểu thực tế của mỗi vế là gì? |
| `variable ... might not have been initialized` | Definite assignment không được bảo đảm | Có đường đi nào dùng biến trước khi gán? |
| `local variables referenced from a lambda ... must be final or effectively final` | Capture biến cục bộ vi phạm quy tắc | Biến bị gán lại sau lúc khởi tạo không? |
| `has private access` | Vi phạm quy tắc truy cập thành viên | Có API công khai/phù hợp thay thế không? |
| `unreported exception ... must be caught or declared` | Vi phạm quy tắc checked exception | Cần `catch` hay khai báo `throws` thích hợp? |

Không nên giải quyết lỗi `incompatible types` bằng ép kiểu bừa bãi. Cast có thể không hợp lệ về ngôn ngữ hoặc tạo lỗi runtime; cần kiểm tra **ý định dữ liệu** trước khi chọn chuyển đổi.

### 10.1. Để javac in chẩn đoán chi tiết

Lệnh ví dụ:

~~~sh
javac -Xdiags:verbose --release 17 -encoding UTF-8 InvalidAssignment.java
~~~

Tùy chọn `-Xdiags:verbose` có thể cung cấp chi tiết chẩn đoán hữu ích, nhất là lỗi overload hoặc generic inference. Nó không biến một chương trình sai kiểu thành đúng kiểu.

Kiểm tra các cờ mà JDK hỗ trợ với `javac --help` và `javac -X`; một số chi tiết dạng lỗi có thể thay đổi theo bản JDK, ngôn ngữ hiển thị hoặc cách build tool thu thập log.

## 11. Ranh giới giữa ngữ nghĩa lúc biên dịch và runtime

Một số điều mà compiler **xác định hoặc kiểm tra**:

- Kiểu tĩnh của biểu thức, kiểu khai báo và khả năng tương thích với ngữ cảnh.
- Tên nào được phân giải thành trường/biến/phương thức nào.
- Overload nào được chọn từ tên, kiểu đối số và target type.
- Các quy tắc widening, boxing, unboxing, cast, generics, wildcard, lambda, switch expression.
- Các ràng buộc flow như definite assignment và effectively final.

Một số điều thường cần **runtime** mới xác định hoặc thực thi:

- Giá trị của biến và điều kiện trong một lần chạy cụ thể.
- Đối tượng thực tế cho một lời gọi virtual được override.
- Một thao tác unboxing có gặp `null` không.
- Một phép cast tham chiếu có thất bại hay không.
- Một phép chia có chia cho 0, hoặc một truy cập array có vượt chỉ số không.
- Kết quả xử lý nghiệp vụ, I/O và tương tác bên ngoài.

Có ngoại lệ và tối ưu hóa: compiler có thể nhận diện **constant expression** và tính giá trị hằng theo quy tắc ngôn ngữ; JVM/JIT có thể tối ưu hóa nhiều phép tính runtime. Tuy vậy, điều đó **không** biến Java thành ngôn ngữ kiểm tra kiểu động, cũng không thay thế các quy tắc compile-time nói trên.

## 12. Bài luyện tập có đáp án định hướng

**Bài 1 — Dự đoán kiểu và lỗi**

~~~java
byte b = 10;
int x = b + 1;
// byte y = b + 1;
byte z = 10 + 1;
double d = 5 / 2;
~~~

Hãy giải thích từng khai báo. Đáp án định hướng: `b + 1` là `int`; `y` sai nếu bỏ comment; `10 + 1` là constant expression có giá trị 11 nên `z` được phép; `d` nhận `2.0`, do phép chia hai `int` diễn ra trước conversion sang `double`.

**Bài 2 — Chọn overload**

~~~java
static void test(Object o) {}
static void test(String s) {}
Object value = "Java";
test(value);
test(null);
~~~

Đặt mã trên trong ngữ cảnh một class/method hợp lệ. Đáp án: `test(value)` chọn `Object` do kiểu tĩnh; `test(null)` chọn `String` do cụ thể hơn. Đổi overload `Object` thành `Integer` thì `test(null)` trở thành mơ hồ.

**Bài 3 — Suy luận kiểu**

Vì sao `Function<String, Integer> length = s -> s.length();` hợp lệ nhưng `var length = s -> s.length();` không hợp lệ? Đáp án: lambda cần **target type** của một functional interface. Ngữ cảnh `var` trong ví dụ không cung cấp kiểu đích đó.

**Bài 4 — Generics**

Vì sao không thể gán trực tiếp `List<Integer>` sang `List<Number>`? Khi cần chỉ đọc các giá trị kiểu `Number` từ danh sách `Integer`, nên cân nhắc `List<? extends Number>`. Hãy chỉ ra điều gì có thể sai nếu được phép thêm `Double` vào danh sách thực tế chứa `Integer`.

**Bài 5 — Rà lỗi có hệ thống**

Cho lỗi `cannot find symbol` trong `service.BookService`, hãy kiểm tra đúng thứ tự: tên khai báo, scope, package/import, quyền truy cập, các tệp nguồn được đưa vào lần gọi `javac`, và classpath/module path cần thiết. Đừng chỉ thay đổi cú pháp cho đến khi không còn thông báo lỗi; cần xác minh compiler đang tìm đúng kiểu mong muốn.

## 13. Checklist khi phân tích một biểu thức

Trước khi kết luận một biểu thức Java đúng hay sai, hãy tự trả lời:

1. Cú pháp AST của biểu thức là gì, các toán hạng và lời gọi nằm ở đâu?
2. Mỗi tên được phân giải thành khai báo nào? Có bị shadowing hoặc không truy cập được không?
3. Kiểu compile-time của từng toán hạng là gì; loại nguyên thủy, tham chiếu hay `null`?
4. Có **target type** từ phép gán, tham số phương thức, `return` hoặc ngữ cảnh khác không?
5. Quy tắc chuyển đổi nào áp dụng: widening, boxing/unboxing, numeric promotion, constant narrowing hay cast?
6. Nếu là lời gọi, những overload nào áp dụng và overload nào cụ thể nhất?
7. Nếu liên quan generics/lambda, ràng buộc suy luận và functional interface có hợp lệ không?
8. Có vi phạm flow, khả năng truy cập, checked exception hoặc quy tắc khác không?
9. Điều gì đã được compiler bảo đảm, và điều gì vẫn chỉ có thể xác định lúc chạy?

**Cốt lõi:** gán ý nghĩa cho biểu thức là biến cây cú pháp thành các thao tác có **ký hiệu, kiểu, phép chuyển đổi và lời gọi được xác định theo Java Language Specification**. Hiểu bước này giúp giải thích chính xác thông báo `javac`, tránh lẫn compile-time với runtime và viết mã Java dễ bảo trì hơn.
