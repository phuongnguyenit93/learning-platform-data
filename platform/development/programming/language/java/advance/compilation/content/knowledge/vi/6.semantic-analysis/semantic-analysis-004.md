# Chuyển đổi kiểu, boxing, unboxing và lỗi chỉ xuất hiện khi chạy

Trong Java, trình biên dịch `javac` kiểm tra **kiểu tĩnh** của biểu thức để quyết định một phép gán, lời gọi phương thức hoặc phép ép kiểu có *được phép* hay không. Khi được phép, Java có thể thực hiện chuyển đổi kiểu ngầm định hoặc tường minh. Một số chuyển đổi bảo toàn giá trị; một số có thể làm mất độ chính xác; một số phải kiểm tra đối tượng thực tế lúc chạy; và **unboxing một tham chiếu `null` có thể ném `NullPointerException`**.

Vì vậy, “`javac` biên dịch thành công” không đồng nghĩa “mọi dữ liệu đưa vào đều chuyển đổi được lúc chạy”. Bài học thuộc phần **Kiểm tra ngữ nghĩa**: hiểu conversion contexts và boxing/unboxing để giải thích ranh giới giữa compile-time error, giá trị chuyển đổi khác mong đợi và runtime exception. Ví dụ sử dụng Java 17+.

## 1. Bức tranh tổng quan: kiểu tĩnh, giá trị runtime và conversion

Hãy phân biệt ba bước:

1. **Kiểu tĩnh**: compiler biết một biểu thức có kiểu khai báo nào (`int`, `Integer`, `Object`, `Number`, ...), và dựa vào quy tắc Java để cho phép hoặc từ chối chuyển đổi.
2. **Chuyển đổi**: trong ngữ cảnh phù hợp, Java có thể chuyển từ primitive sang primitive, primitive sang wrapper, wrapper sang primitive hoặc một reference type sang reference type.
3. **Giá trị tại runtime**: một biến `Object` có thể đang trỏ tới `String`, `Integer` hoặc `null`. Chuyển đổi kiểu tham chiếu cần kiểm tra runtime thì chỉ thành công nếu đối tượng thực tế tương thích; unboxing chỉ chạy được khi reference không phải `null`.

~~~text
Java source (.java)
       │
       ▼
javac: xét kiểu tĩnh, quy tắc conversion, overload, generic
       │
       ├── Không thể chuyển đổi hợp lệ ──► compile-time error
       │
       ▼
class file (.class)
       │
       ▼
JVM: thực hiện phép toán và các chuyển đổi cần tại runtime
       │
       ├── Giá trị phù hợp ──────────────► kết quả
       ├── null được unbox ─────────────► NullPointerException
       └── cast reference sai kiểu ─────► ClassCastException
~~~

Trong JLS, các loại chuyển đổi chính bao gồm **identity, widening/narrowing primitive, widening/narrowing reference, boxing, unboxing, unchecked, capture và string conversion**. Không phải loại nào cũng áp dụng được ở mọi ngữ cảnh. Phép gán, lời gọi phương thức, phép cast và toán tử số có những tập chuyển đổi được phép khác nhau.

## 2. Chuyển đổi giữa các kiểu primitive

### 2.1. Widening primitive: mở rộng miền biểu diễn

Ví dụ thường gặp:

~~~java
int count = 42;
long total = count;      // int -> long, ngầm định
double measure = total;  // long -> double, ngầm định
~~~

Những chuyển đổi như `byte → short → int → long`, `int → double` hoặc `float → double` thường không cần cast. Nhưng **widening không luôn bảo toàn chính xác số học**: chuyển `long` rất lớn sang `float` hoặc `double` có thể bị làm tròn do giới hạn số chữ số có nghĩa. “Widening” nói về quy tắc kiểu được phép, không phải lời hứa giá trị nguyên vẹn trong mọi trường hợp.

Mọi phép gán cũng phải tôn trọng bảng conversion: `boolean` không tham gia chuyển đổi số; `char` là kiểu số nguyên không dấu 16-bit trong ngữ cảnh numeric conversion, nhưng `char` không thể tự động nhận từ `short`.

### 2.2. Narrowing primitive: ép kiểu có thể mất thông tin

Một giá trị `int` có thể vượt miền `byte` (-128 đến 127), nên chuyển theo hướng thu hẹp thường phải cast rõ ràng:

~~~java
int value = 130;
byte narrowed = (byte) value;
System.out.println(narrowed); // -126
~~~

`(byte) 130` lấy phần biểu diễn phù hợp độ rộng 8-bit, nên kết quả là `-126`. Phép cast hợp lệ nhưng **không báo exception** khi mất phần giá trị. Đây là ví dụ quan trọng: không phải mọi conversion “nguy hiểm” đều thất bại tại runtime; có conversion thành công và tạo ra giá trị khác dự định.

Ngoại lệ hữu ích trong **assignment context**: biểu thức hằng kiểu `int` nằm trong miền biểu diễn có thể gán trực tiếp cho `byte`/`short`/`char` và trong một số trường hợp các wrapper tương ứng.

~~~java
byte small = 100;       // Hợp lệ: int constant expression vừa miền byte
char letter = 65;       // Hợp lệ: int constant expression vừa miền char
// byte tooBig = 128;   // Lỗi biên dịch: không vừa miền byte

int dynamic = 100;
// byte b = dynamic;     // Lỗi biên dịch: dynamic không phải constant expression
byte b = (byte) dynamic; // Hợp lệ nhờ cast
~~~

**Không khái quát quy tắc hằng số này cho mọi ngữ cảnh.** Ví dụ, `void accept(byte b)` không được gọi bằng `accept(100)` chỉ nhờ `100` vừa miền byte: method invocation context không có phép narrowing hằng `int` giống assignment context.

### 2.3. Chuyển từ floating-point sang integral

Cast từ `double`/`float` sang `int`/`long` không đơn giản là “ném ngoại lệ nếu ngoài miền”:

- Phần thập phân bị bỏ về phía 0 khi kết quả nằm trong miền biểu diễn.
- Với giá trị hữu hạn quá lớn hoặc quá nhỏ, phép chuyển sang integral đích rộng tương ứng được giới hạn về đầu mút rồi có thể tiếp tục thu hẹp theo kiểu đích.
- `NaN` chuyển sang kiểu số nguyên thành 0.
- Không có `ArithmeticException` chỉ vì explicit cast này mất dữ liệu.

~~~java
public class NumericConversionDemo {
    public static void main(String[] args) {
        System.out.println((int) 3.9);
        System.out.println((int) -3.9);
        System.out.println((int) Double.NaN);
        System.out.println((int) Double.POSITIVE_INFINITY);
        System.out.println((byte) 130);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NumericConversionDemo.java
java NumericConversionDemo
~~~

Stdout chính xác:

~~~text
3
-3
0
2147483647
-126
~~~

Lưu ý một số phép chuyển theo JLS có hai bước, như `double` sang `byte`: từ floating sang `int` rồi từ `int` sang `byte`. Không nên thay quy tắc cụ thể bằng suy đoán “JVM luôn truncate bit”.

## 3. Numeric promotion và toán tử số học

Khi dùng `+`, `-`, `*`, `/`, toán tử so sánh số và nhiều toán tử khác, Java áp dụng **numeric promotion** thích hợp để đưa toán hạng về kiểu được sử dụng cho phép toán.

Một trường hợp thường gặp: `byte`, `short` và `char` được promote lên `int` trong phép toán hai ngôi thông thường.

~~~java
byte a = 10;
byte b = 20;
// byte sum = a + b;     // Lỗi: a + b có kiểu int
int sum = a + b;         // Hợp lệ
byte narrowSum = (byte) (a + b);
~~~

`byte` trong biến không có nghĩa mọi phép tính với nó cũng trả về `byte`. Tương tự, `char + 1` là biểu thức số nguyên; nếu muốn gán lại `char` phải chọn quy tắc chuyển đổi phù hợp.

Với compound assignment, Java có conversion ẩn:

~~~java
byte n = 127;
n += 1;                   // Tương đương về giá trị: n = (byte) (n + 1)
System.out.println(n);    // -128
~~~

`n = n + 1` không hợp lệ vì biểu thức bên phải có kiểu `int`. Còn `n += 1` hợp lệ, nhưng **vẫn có thể làm tràn/thu hẹp giá trị**. Các toán tử compound assignment không miễn trừ quy tắc số học.

Với các kiểu số nguyên 32/64-bit, cộng/trừ/nhân quá miền biểu diễn thông thường **không ném exception** mà tràn theo biểu diễn Java; nếu muốn phát hiện tràn, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` hoặc kỹ thuật kiểm tra miền thích hợp. Chia số nguyên cho 0 là ví dụ lỗi runtime khác: `ArithmeticException`.

## 4. Boxing: primitive thành wrapper

Tám cặp thường gặp là:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

**Boxing** là conversion từ giá trị primitive sang reference của wrapper tương ứng. Ví dụ:

~~~java
int primitive = 42;
Integer boxed = primitive;      // Autoboxing
Integer explicit = Integer.valueOf(primitive);
Object asObject = primitive;    // Boxing int -> Integer, rồi widening reference -> Object
~~~

Autoboxing trong source có hiệu ứng giá trị tương đương nhận wrapper cho primitive, thường được compiler hạ thành lời gọi kiểu `Integer.valueOf(...)`. Tuy nhiên, không suy luận rằng mỗi boxing chắc chắn phân bổ một object mới: wrapper có thể cache instance. Hơn nữa, boxing có thể cần tài nguyên bộ nhớ, dù lỗi thông thường mà người học gặp liên quan conversion thường là lỗi khi **unboxing null**, không phải chính boxing.

**Không có chuỗi “widen primitive rồi boxing” tự động trong assignment thông thường**:

~~~java
Integer good = 10;      // int -> Integer
Long alsoGood = 10L;    // long -> Long
// Long bad = 10;       // Compile-time error: không tự int -> long -> Long
~~~

Nếu cần `Long`, dùng literal `10L`, hoặc chuyển/khởi tạo rõ kiểu (ví dụ `Long.valueOf(10L)`).

Boxing còn xuất hiện khi gọi API nhận object hoặc khi đưa primitive vào generic collections:

~~~java
import java.util.ArrayList;
import java.util.List;

class BoxingWithList {
    static List<Integer> values() {
        List<Integer> result = new ArrayList<>();
        result.add(7); // int -> Integer
        return result;
    }
}
~~~

Generic type argument `Integer` là reference type, không thể viết `List<int>` trong Java 17. Java Collections lưu tham chiếu tới wrapper, đồng thời có thể phát sinh boxing/unboxing khi lấy và tính toán dữ liệu.

## 5. Unboxing: wrapper thành primitive

**Unboxing** lấy giá trị primitive từ wrapper:

~~~java
Integer boxed = 21;
int unboxed = boxed;            // Integer -> int
int explicit = boxed.intValue();
long promoted = boxed;          // Integer -> int -> long
~~~

Unboxing có thể xảy ra mà source không ghi `intValue()`, ví dụ ở assignment, phép toán và một số lời gọi phương thức.

~~~java
Integer left = 20;
Integer right = 22;
int sum = left + right;         // Hai unboxing, sau đó cộng int
~~~

Điểm khác biệt quan trọng: **wrapper là tham chiếu và có thể bằng `null`**, trong khi primitive `int`, `long`, `boolean`... không nhận giá trị `null`.

~~~java
Integer maybe = null;
// int n = maybe;         // Biên dịch được, nhưng chạy sẽ ném NullPointerException
~~~

Dòng có dấu `//` đang tắt chỉ để trình diễn; nếu bật lên và chạy tới, nó sẽ ném `NullPointerException` tại thời điểm unboxing. `javac` cho phép vì kiểu tĩnh `Integer` có thể chuyển thành `int`; compiler nói chung không bảo đảm tham chiếu có giá trị khác `null` trên mọi nhánh runtime.

### Những chỗ unboxing ẩn cần nhìn thấy

~~~java
Integer number = null;
Boolean flag = null;

// if (number > 0) { }    // Integer -> int: NPE nếu number null
// if (number == 0) { }   // So sánh Integer với int: NPE
// int x = number + 1;    // Toán tử số: NPE
// if (flag) { }          // Boolean -> boolean: NPE
// boolean b = !flag;     // Phủ định boolean: NPE
~~~

Đáng chú ý: `number == null` chỉ so sánh tham chiếu với `null`, **không cần unbox**, và là cách kiểm tra an toàn. Cũng vậy, nối chuỗi `"value=" + number` có thể in `"value=null"` mà không buộc unbox, vì đó là string conversion.

## 6. Ví dụ thực hành: code biên dịch được, lỗi chỉ khi chạy

Tệp `RuntimeConversionDemo.java`:

~~~java
public class RuntimeConversionDemo {
    static int increment(Integer value) {
        return value + 1; // Unboxing khi đánh giá phép cộng
    }

    public static void main(String[] args) {
        System.out.println(increment(41));

        try {
            Integer missing = null;
            System.out.println(increment(missing));
        } catch (NullPointerException ex) {
            System.out.println("Caught: NullPointerException");
        }

        Object value = "hello";
        try {
            Integer count = (Integer) value;
            System.out.println(count);
        } catch (ClassCastException ex) {
            System.out.println("Caught: ClassCastException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RuntimeConversionDemo.java
java RuntimeConversionDemo
~~~

Stdout chính xác:

~~~text
42
Caught: NullPointerException
Caught: ClassCastException
~~~

Phân tích:

- `increment(41)` hợp lệ: primitive `int` được boxing thành `Integer` khi gọi `increment(Integer)`. Lúc xử lý `value + 1`, wrapper được unboxing về `int`.
- `increment(null)` cũng hợp lệ về **kiểu tĩnh** vì parameter là reference `Integer`, nhưng khi tính `value + 1` với `value == null` thì unboxing ném `NullPointerException`.
- `Object value = "hello"` là widening reference từ `String` sang `Object`. Cast `(Integer) value` được compiler chấp nhận về mặt khả năng ép kiểu, nhưng JVM kiểm tra đối tượng thực tế: `String` không phải `Integer`, nên ném `ClassCastException`.
- `try/catch` trong ví dụ chỉ dùng để quan sát hai loại exception và tiếp tục in output. Với hệ thống thực tế nên ngăn lỗi bằng hợp đồng input và validation phù hợp, không dùng exception như cách xử lý thông thường cho mọi chuyển đổi.

## 7. Widening và narrowing reference: khác primitive conversion

Widening reference đi từ subtype sang supertype phù hợp, thường không cần runtime check:

~~~java
Integer integer = 9;
Number number = integer; // Integer -> Number
Object object = number;   // Number -> Object
~~~

Đối tượng thực tế vẫn là `Integer`. Chuyển `Number` thành `Object` không làm biến đối tượng thành một instance `Object` mới hay đổi danh tính.

Narrowing reference đi theo chiều cần kiểm tra cụ thể hơn:

~~~java
Object value = "Java";
String text = (String) value; // Runtime thành công

Object another = Integer.valueOf(10);
// String wrong = (String) another; // Compile được, runtime ClassCastException
~~~

Nếu compiler chứng minh hai kiểu không thể chuyển đổi theo bất cứ đối tượng hợp lệ nào, nó từ chối cast ngay từ compile time. Ví dụ cast trực tiếp từ `String` sang `Integer` là inconvertible types và bị từ chối; qua biến `Object` thì có thể hợp lệ về mặt cú pháp và typing nhưng bị kiểm tra lúc chạy.

`instanceof` giúp kiểm tra kiểu thực trước khi lấy thông tin phụ thuộc vào subtype:

~~~java
Object input = "Java 17";
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

Stdout đoạn này nếu đặt trong `main` là `7`. Java 17 hỗ trợ pattern matching cho `instanceof`; với `null`, `instanceof String` trả `false`. Đây là cách giảm cast nguy hiểm khi input có nhiều kiểu hợp lệ. Không thay thế validation cho nội dung dữ liệu, và không chứng minh mọi generic type argument vì erasure.

## 8. Overload resolution: widening khác boxing

Một điểm liên quan trực tiếp đến kiểm tra ngữ nghĩa của `javac` là **chọn overload tại compile time**. Java thử các method applicability phase (strict invocation trước, rồi loose invocation nếu cần, sau đó variable arity). Trong trường hợp đơn giản, một lời gọi có thể ưu tiên primitive widening trước boxing, dù boxing cũng có vẻ phù hợp.

Tệp `OverloadConversionDemo.java`:

~~~java
public class OverloadConversionDemo {
    static void choose(long x) {
        System.out.println("long");
    }

    static void choose(Integer x) {
        System.out.println("Integer");
    }

    static void accept(Number x) {
        System.out.println("Number");
    }

    public static void main(String[] args) {
        choose(10);                // int -> long ở strict invocation phase
        choose(Integer.valueOf(10)); // Integer phù hợp trực tiếp
        accept(10);                // int -> Integer -> Number
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OverloadConversionDemo.java
java OverloadConversionDemo
~~~

Stdout chính xác:

~~~text
long
Integer
Number
~~~

Việc chọn method không căn cứ vào một quy tắc đơn giản kiểu “widen luôn hơn box” ở mọi overload; danh sách chữ ký, generic, varargs, subtype và độ đặc hiệu của lời gọi đều quan trọng. Quy trình này cũng khác với dynamic dispatch: overload **chọn signature ở compile time**, còn override của instance method có thể được dispatch động khi chạy.

Không cố “sửa” overload bằng cách cast bừa. Nếu API gây mơ hồ hoặc quá khó dự đoán, đặt tên method rõ mục đích hoặc khai báo tham số nhất quán thường dễ bảo trì hơn.

## 9. Conditional operator và NullPointerException bất ngờ

Toán tử điều kiện `condition ? a : b` **chỉ đánh giá một trong hai nhánh**, nhưng kiểu kết quả được compiler xác định từ **kiểu của cả hai nhánh**. Điều đó có thể buộc unboxing giá trị của nhánh được chọn.

~~~java
Integer absent = null;
boolean useFallback = true;
int safe = useFallback ? 1 : absent; // Kết quả 1; nhánh absent không được đánh giá
~~~

Nếu `useFallback` là `false`, nhánh `absent` được chọn và bị unboxing thành `int` theo quy tắc kiểu của numeric conditional expression, gây NPE. Đừng suy luận rằng “một nhánh là `Integer` nên cả biểu thức là `Integer`”.

Ví dụ chạy được:

~~~java
public class TernaryUnboxingDemo {
    public static void main(String[] args) {
        Integer missing = null;
        System.out.println(true ? 1 : missing);
        try {
            System.out.println(false ? 1 : missing);
        } catch (NullPointerException ex) {
            System.out.println("ternary: NullPointerException");
        }
    }
}
~~~

~~~bash
javac --release 17 TernaryUnboxingDemo.java
java TernaryUnboxingDemo
~~~

Stdout:

~~~text
1
ternary: NullPointerException
~~~

Cách xử lý phổ biến khi cần số primitive có fallback là kiểm tra `null` rõ ràng:

~~~java
Integer input = null;
int result = input == null ? 0 : input;
System.out.println(result); // 0
~~~

Nếu business logic cần phân biệt “không có dữ liệu” và giá trị `0`, hãy giữ wrapper/`OptionalInt` hoặc biểu diễn domain thích hợp thay vì gộp hai trạng thái.

## 10. So sánh wrapper: giá trị khác identity

Toán tử `==` với **hai reference wrapper** kiểm tra có cùng object hay không; với **một wrapper và một primitive cùng nhóm số tương ứng**, numeric promotion thường dẫn tới unboxing và so sánh giá trị primitive.

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true, bằng giá trị
System.out.println(a == 1000);    // true, unbox rồi so sánh số
~~~

Đừng lấy `a == b` làm kiểm tra giá trị. Một số wrapper có cache và Java quy định tính đồng nhất reference trong các trường hợp boxing giá trị nhỏ nhất định; ví dụ kiểm tra identity trên số nhỏ có thể trông đúng, rồi sai khi dữ liệu lớn hoặc khác môi trường. Không nên dựa trên chi tiết cache để thiết kế logic.

Với reference có thể `null`:

~~~java
Integer maybe = null;
System.out.println(maybe == null); // true, không unbox
// System.out.println(maybe == 0); // NPE nếu bỏ chú thích
~~~

Có thể dùng `java.util.Objects.equals(a, b)` để so sánh hai wrapper theo giá trị một cách an toàn với `null`. Với so sánh thứ tự (<, >), primitive là lựa chọn tốt khi dữ liệu bắt buộc tồn tại; nếu dùng wrapper nullable cần xác định chính sách xử lý trước khi làm phép toán.

## 11. Generic erasure: cast có thể bị hoãn tới lúc đọc phần tử

Java generics hỗ trợ kiểm tra kiểu ở compile time, nhưng **type erasure** khiến runtime không kiểm tra đầy đủ `List<String>` đối với từng phần tử trong mọi đường đi. Chỉ cần raw type hoặc unchecked cast phá vỡ bảo đảm, lỗi có thể xuất hiện **lúc đọc dữ liệu**.

Tệp `HeapPollutionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List raw = names;
        raw.add(Integer.valueOf(5)); // Raw type bỏ qua kiểm tra String ở compile time

        try {
            String name = names.get(0); // Cast sinh bởi compiler tới String
            System.out.println(name);
        } catch (ClassCastException ex) {
            System.out.println("generic: ClassCastException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 HeapPollutionDemo.java
java HeapPollutionDemo
~~~

Stdout:

~~~text
generic: ClassCastException
~~~

Compiler đã đặt type check phù hợp khi đọc `String name = names.get(0)`; nó không liên tục kiểm chứng danh sách chỉ chứa String lúc runtime. `@SuppressWarnings` trong ví dụ chỉ để cô lập hành vi; khi viết mã thực tế, **không nên che cảnh báo raw/unchecked** trừ khi đã có một ranh giới chuyển đổi được kiểm soát. Các warning compile-time là tín hiệu cần xử lý để tránh lỗi runtime xa chỗ gây ra.

Một cast kiểu `(List<String>) obj` cũng không có khả năng xác minh chính xác từng type argument chỉ nhờ runtime erasure; generic collection không tự “thành List<String> sạch” sau khi cast.

## 12. Array covariance: hợp lệ tại compile time, ArrayStoreException lúc chạy

Array của reference type có **covariance**: `String[]` có thể gán cho `Object[]`. Nhưng object array vẫn biết component type thực tế tại runtime, nên việc ghi phần tử sai kiểu sẽ bị chặn.

~~~java
public class ArrayStoreDemo {
    public static void main(String[] args) {
        Object[] items = new String[1];
        try {
            items[0] = Integer.valueOf(7);
        } catch (ArrayStoreException ex) {
            System.out.println("array: ArrayStoreException");
        }
    }
}
~~~

~~~bash
javac --release 17 ArrayStoreDemo.java
java ArrayStoreDemo
~~~

Stdout:

~~~text
array: ArrayStoreException
~~~

Compiler thấy `items` có kiểu tĩnh `Object[]` nên một `Integer` là giá trị `Object` hợp lệ để gán ở source. JVM lại biết array thực là `String[]` và kiểm tra element khi ghi. Đây là **lỗi kiểm tra kiểu runtime khác** với `ClassCastException`. Không suy ra generic `List<Number>` cũng nhận `List<Integer>`: generic type arguments của Java thường invariant.

## 13. Phân biệt lỗi runtime với việc mất giá trị không ném exception

Không phải mọi kết quả xấu đều ném exception, và không phải mọi runtime exception đều bắt nguồn từ casting.

| Tình huống | Compile time | Khi thực thi |
| --- | --- | --- |
| `byte b = 128;` | **Lỗi**: hằng không vừa miền byte | Không chạy được |
| `byte b = (byte) 128;` | **Hợp lệ** | Giá trị là `-128`, không exception |
| `int n = (int) Double.NaN;` | **Hợp lệ** | `n == 0` |
| `Integer n = null; int x = n;` | **Hợp lệ** | `NullPointerException` khi unbox |
| `Object x = "hi"; Integer n = (Integer) x;` | **Hợp lệ** | `ClassCastException` |
| `Object[] a = new String[1]; a[0] = 1;` | **Hợp lệ** | `ArrayStoreException` |
| `int x = Integer.MAX_VALUE + 1;` | **Hợp lệ** | Kết quả `-2147483648`; không exception |
| `Math.addExact(Integer.MAX_VALUE, 1)` | **Hợp lệ** | `ArithmeticException` |
| `Long n = 1;` | **Lỗi**: không được implicit int → long → Long | Không chạy được |

Ví dụ tổng hợp — `OverflowDemo.java`:

~~~java
public class OverflowDemo {
    public static void main(String[] args) {
        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println(wrapped);

        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("checked: ArithmeticException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OverflowDemo.java
java OverflowDemo
~~~

Stdout:

~~~text
-2147483648
checked: ArithmeticException
~~~

Nếu cần bảo đảm không mất dữ liệu trong chuyển đổi số nguyên, hãy **kiểm tra miền hợp lệ trước khi cast**. Nếu xử lý cộng nhân mà tràn là lỗi nghiệp vụ, ưu tiên exact arithmetic hoặc kiểu dữ liệu có miền phù hợp. Nếu dữ liệu ngoài hệ thống có thể `null`, kiểm tra null trước unboxing, đặc biệt ở boundary HTTP/JSON/database.

## 14. Những lỗi compile time mà javac phát hiện sớm

Tệp `InvalidConversions.java` dưới đây là **mã cố ý không biên dịch**. Không chạy chung với các ví dụ hợp lệ:

~~~java
class InvalidConversions {
    void demo() {
        int primitive = 5;
        // boolean flag = primitive; // Java không chuyển int thành boolean

        // Integer n = "5";          // String không gán được cho Integer
        // byte b = primitive;        // int biến -> byte cần cast
        // Long big = 5;              // Không có ngầm định int -> long -> Long
        // int fromNull = null;       // Không có chuyển null trực tiếp vào primitive

        String s = "ok";
        // Integer impossible = (Integer) s; // Hai kiểu class final không cast trực tiếp được
    }
}
~~~

Các dòng lỗi được comment để tập trung vào ý nghĩa. Nếu bỏ dấu `//` ở từng dòng tương ứng, `javac` sẽ báo lỗi compile time. Khác với ví dụ `Object x = "hi"; Integer n = (Integer) x;`, compiler thấy ngay biến `s` có kiểu `String` nên không có narrowing reference conversion trực tiếp phù hợp sang `Integer`.

**Đọc thông báo lỗi theo ngữ cảnh:** compiler có thể báo `incompatible types`, `possible lossy conversion` hoặc `inconvertible types`; câu chữ và vị trí chính xác có thể khác theo phiên bản JDK. Điều quan trọng là luật conversion nào bị vi phạm.

## 15. Nhìn vào bytecode để thấy chuyển đổi xảy ra

Có thể dùng `javap` để quan sát phương thức đã compile:

~~~bash
javac --release 17 RuntimeConversionDemo.java
javap -c -p RuntimeConversionDemo
~~~

Với mã Java dùng boxing/unboxing, bytecode trên các bản `javac` thông dụng có thể cho thấy lời gọi như `Integer.valueOf(int)` và `Integer.intValue()`. Narrowing reference cast thường có instruction `checkcast`. Số học primitive dùng instruction phù hợp như `iadd`.

Không cần thuộc lòng thứ tự instruction để hiểu lỗi; chỉ cần nắm:

- **Compile time** xác định một phép chuyển có hợp lệ theo kiểu tĩnh và có thể chèn thao tác chuyển đổi.
- **Runtime** thực hiện các thao tác đó trên giá trị thực tế; `null` hoặc reference sai kiểu có thể ném exception.
- **Erasure** có thể dẫn tới cast bổ sung khi dùng generic.
- **Primitive narrowing** có thể tạo giá trị khác ý định mà không ném exception.

Dạng bytecode cụ thể có thể khác giữa các JDK, nên coi output `javap` là dữ liệu kiểm chứng của **một lần biên dịch cụ thể**, không phải văn bản bắt buộc giữ nguyên trên mọi phiên bản.

## 16. Cách viết code giảm lỗi chuyển đổi

1. **Ưu tiên primitive** nếu dữ liệu luôn tồn tại và không cần `null`: `int`/`long` tránh boxing không cần thiết và NPE do unboxing.
2. **Dùng wrapper có chủ đích** khi dữ liệu có thể vắng mặt hoặc API yêu cầu reference; đặt quy ước null rõ ràng và kiểm tra ở boundary.
3. **Đừng dùng `==` cho hai wrapper để so sánh giá trị**; dùng `equals`/`Objects.equals`, hoặc unbox an toàn rồi so sánh primitive.
4. **Hạn chế raw type và unchecked cast**: giữ generic type information ở source; xử lý warning thay vì che toàn bộ.
5. **Kiểm tra kiểu trước narrowing reference cast** khi nhận `Object` hoặc dữ liệu đa hình (`instanceof`, pattern matching).
6. **Chọn phép chuyển số có kiểm soát**: kiểm tra phạm vi nếu cast narrowing, dùng `Math.toIntExact(long)` để phát hiện `long` ngoài miền `int` (ném `ArithmeticException`), hoặc `Math.addExact` khi cần bắt overflow.
7. **Viết test theo ranh giới**: `null`, số âm, `0`, min/max, phần tử collection sai kiểu, các overload gần nhau, giá trị khác miền và nhánh điều kiện hiếm gặp.

Ví dụ cách biểu đạt ý định conversion rõ ràng:

~~~java
import java.util.Objects;

public class SafeConversions {
    static int required(Integer number) {
        return Objects.requireNonNull(number, "number must not be null");
    }

    static long widen(int value) {
        return value;
    }

    static int checkedNarrow(long value) {
        return Math.toIntExact(value);
    }
}
~~~

`required` ném NPE với thông điệp rõ hơn khi đầu vào null; `widen` là chuyển `int` sang `long` không mất giá trị; `checkedNarrow` phát hiện số `long` nằm ngoài miền `int`. Đây là các phương thức hợp lệ với Java 17, có thể biên dịch bằng `javac SafeConversions.java` nhưng không có `main` nên không phải chương trình tự chạy.

## 17. Bài tập tự kiểm tra

**Bài 1.** Đoán kết quả và giải thích vì sao:

~~~java
byte x = 127;
x += 1;
System.out.println(x);
~~~

**Đáp án:** `-128`. Compound assignment cho phép narrowing ẩn; biến byte tràn theo biểu diễn 8-bit.

**Bài 2.** Đoạn sau lỗi ở compile time hay runtime?

~~~java
Object o = Integer.valueOf(5);
String s = (String) o;
~~~

**Đáp án:** Compile thành công; khi chạy tới cast sẽ ném `ClassCastException`. Kiểu tĩnh của `o` là `Object`, nhưng đối tượng thực là `Integer`.

**Bài 3.** `Long value = 5;` có được tự chuyển từ int thành long rồi boxing không?

**Đáp án:** Không. Đây là lỗi compile time. Dùng `5L` hoặc khởi tạo wrapper từ long rõ ràng.

**Bài 4.** Vì sao `Integer n = null; if (n == null) ...` an toàn nhưng `if (n == 0) ...` có thể lỗi?

**Đáp án:** So sánh reference với `null` không unbox; so sánh với primitive numeric `0` yêu cầu unbox `n`, dẫn tới NPE nếu n null.

**Bài 5.** Hai biến `Integer` cùng giá trị 1000 có nên so bằng `==` không?

**Đáp án:** Không. `==` giữa hai reference kiểm tra identity; `equals` so sánh giá trị số. Không dựa vào cache wrapper.

**Bài 6.** Vì sao `Object[] a = new String[1]; a[0] = Integer.valueOf(5);` hợp lệ ở compile time nhưng thất bại khi chạy?

**Đáp án:** Kiểu tĩnh là `Object[]` cho phép gán reference `Integer`; runtime array thực tế là `String[]`, nên JVM ném `ArrayStoreException`.

**Bài 7.** Đâu là sự khác nhau giữa `(int) Double.POSITIVE_INFINITY` và `Math.toIntExact(Long.MAX_VALUE)`?

**Đáp án:** Cast floating sang `int` cho giá trị `Integer.MAX_VALUE`, không exception. `Math.toIntExact` kiểm tra giá trị `long` có vừa miền `int` không và ném `ArithmeticException` nếu ngoài miền.

## 18. Checklist khi gặp lỗi liên quan chuyển đổi

- Xác định **kiểu tĩnh** của từng toán hạng, đừng chỉ nhìn object thực tế.
- Xác định ngữ cảnh: **assignment**, **method invocation**, **casting**, **numeric** hay **conditional expression**.
- Hỏi chuyển đổi thuộc nhóm nào: primitive widening/narrowing, reference widening/narrowing, boxing, unboxing hoặc chuỗi conversion được phép.
- Nếu `javac` từ chối, đọc lỗi kiểu/overload và kiểm tra có cố implicit narrowing hoặc widen-then-box không.
- Nếu compile được nhưng chạy lỗi, kiểm tra **reference có `null` không**, cast runtime tới kiểu nào, có raw generic hay array covariance không.
- Nếu không ném exception nhưng dữ liệu sai, kiểm tra **overflow**, truncation và precision loss.
- Chạy ví dụ tối giản với `javac --release 17` rồi dùng `javap -c` khi cần quan sát conversion compiler phát ra.

**Ghi nhớ:** `javac` xác minh **phép chuyển được phép về mặt kiểu**, nhưng một số phép chuyển được kiểm tra trên **giá trị thực lúc chạy**. Boxing tự động giúp API tiện hơn, còn unboxing nullable và narrowing reference cast là nguồn lỗi runtime điển hình. Với chuyển đổi số, nguy cơ thường là **mất giá trị mà không có exception**; muốn bảo đảm, phải kiểm tra miền và yêu cầu của ứng dụng.

Tham khảo đặc tả chuẩn: [JLS Java SE 17 §5 – Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html), [JLS §15.12 – Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12), [JLS §15.25 – Conditional Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25), và [JLS §10.5 – Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).