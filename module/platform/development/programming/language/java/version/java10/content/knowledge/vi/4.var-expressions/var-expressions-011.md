# Boxing, unboxing và chuyển đổi số trong biểu thức khởi tạo với `var`

## 1. Bài toán: kiểu của biến `var` đến từ biểu thức nào?

Từ **Java 10**, `var` cho phép trình biên dịch suy luận kiểu của một biến cục bộ từ **biểu thức khởi tạo**. Khi biểu thức chứa các số nguyên thủy, đối tượng wrapper hoặc phép toán hỗn hợp, cần hiểu ba cơ chế liên quan:

1. **Boxing**: chuyển giá trị primitive sang đối tượng wrapper tương ứng, chẳng hạn `int` sang `Integer`.
2. **Unboxing**: lấy giá trị primitive từ wrapper, chẳng hạn `Integer` sang `int`.
3. **Chuyển đổi số và numeric promotion**: xác định kiểu dùng để tính một phép toán, chẳng hạn `byte + short` thường cho `int`, còn `int + long` cho `long`.

Đây đều là quy tắc ngôn ngữ và thư viện **vẫn áp dụng trong Java hiện đại**. `var` không thay đổi chúng: **trình biên dịch xác định kiểu của initializer theo quy tắc Java, sau đó dùng kiểu ấy cho biến được khai báo**.

Bài học tập trung vào **“Boxing, unboxing và chuyển đổi số trong biểu thức khởi tạo”**, trong ngữ cảnh cha **“var và biểu thức”**. Các ví dụ dùng Java 17+ và thư viện chuẩn còn được hỗ trợ.

### Sau bài học, bạn cần làm được

- Phân biệt kiểu `int` và `Integer` của biến được khai báo bằng `var`.
- Giải thích khi nào một phép toán với wrapper xảy ra unboxing, và kết quả của phép toán có kiểu gì.
- Dự đoán `var` suy luận `int`, `long`, `float` hay `double` trong phép toán số.
- Giải thích khác biệt giữa **chuyển đổi trước phép tính** và **ép kiểu sau phép tính**, nhất là chia nguyên và tràn số.
- Nhận biết nguy cơ `NullPointerException` khi unboxing một wrapper chứa `null`.
- Đọc và chạy chương trình kiểm chứng kiểu, giá trị và các lỗi thường gặp.

## 2. Phân biệt primitive và wrapper

Các kiểu số primitive và wrapper liên quan trực tiếp:

| Primitive | Wrapper | Ví dụ nhận giá trị wrapper |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 2)` |
| `short` | `Short` | `Short.valueOf((short) 2)` |
| `int` | `Integer` | `Integer.valueOf(2)` |
| `long` | `Long` | `Long.valueOf(2L)` |
| `float` | `Float` | `Float.valueOf(2.0f)` |
| `double` | `Double` | `Double.valueOf(2.0)` |
| `char` | `Character` | `Character.valueOf('A')` |

`Boolean` cũng là wrapper của `boolean`, nhưng không phải kiểu số; nó xuất hiện trong các biểu thức logic, không tuân theo phép cộng số học.

**Primitive** lưu giá trị theo kiểu primitive (`int`, `double`, ...). **Wrapper** là một đối tượng tham chiếu (`Integer`, `Double`, ...), nên có thể là `null` và thường xuất hiện trong các generic collection: `List<Integer>`, `Map<String, Double>`. Thực tế, generic của Java không dùng trực tiếp tham số kiểu primitive như `List<int>`.

Wrapper **không phải phép thay thế hoàn toàn giống primitive**: nó có đặc tính reference, có thể chứa `null`, có phương thức và có chi phí tạo/lưu trữ hoặc unboxing tùy ngữ cảnh. Với dữ liệu số thường xuyên tính toán, primitive thường phù hợp hơn khi không cần khả năng vắng mặt.

## 3. Boxing: chuyển primitive thành wrapper

### 3.1. Boxing trong ngữ cảnh gán

~~~java
// Các câu lệnh minh họa đặt trong phương thức:
int count = 7;
Integer boxed = count;  // boxing conversion: int -> Integer

Long boxedLong = 7L;    // boxing conversion: long -> Long
~~~

Compiler có thể thực hiện boxing conversion khi kiểu đích là wrapper thích hợp. Cách viết `Integer boxed = count;` biểu đạt rõ: biến `boxed` có kiểu `Integer`.

Trong code hiện đại, có thể tạo wrapper qua factory method:

~~~java
var boxed = Integer.valueOf(7);
~~~

Ở đây `Integer.valueOf(7)` **trả về `Integer`**; do đó `var boxed` suy luận **`Integer`**. Đừng đánh đồng lời gọi factory method với việc tự động boxing của toàn bộ khai báo: initializer đã có kiểu wrapper.

**Không cần dùng constructor wrapper lỗi thời** như `new Integer(7)`. Các factory method `valueOf` và automatic boxing vẫn là kiến thức hữu ích.

### 3.2. `var` không tự boxing literal

Hai khai báo này **khác kiểu**:

~~~java
var primitive = 7;                 // int
var wrapper = Integer.valueOf(7);  // Integer
~~~

Initializer literal `7` có kiểu `int`. Vì không có một kiểu wrapper được khai báo ở vế trái, `var primitive = 7;` không tự sinh yêu cầu boxing để biến thành `Integer`.

So sánh:

~~~java
Integer explicitTarget = 7;  // có kiểu đích Integer: boxing
var inferredPrimitive = 7;   // suy luận int, không boxing để tạo biến
var inferredWrapper = Integer.valueOf(7); // suy luận Integer
~~~

Quy tắc ghi nhớ: **muốn biết kiểu của `var`, hãy hỏi initializer có kiểu gì sau các phép chuyển đổi trong chính biểu thức; đừng tự chèn boxing vì tưởng `var` là kiểu Object**.

### 3.3. Boxing không đồng nghĩa mọi phép chuyển đổi đều hợp lệ

~~~java
Long valid = 7L;     // long -> Long
// Long invalid = 7; // lỗi: literal int không tự widening rồi boxing thành Long
~~~

`7` là `int`, còn `7L` là `long`. Nếu cần `Long`, dùng giá trị `long` phù hợp (ví dụ `7L`) hoặc phương thức trả về `Long`. Không giả định Java luôn tự nối nhiều bước chuyển đổi theo ý muốn.

Đối với `var`:

~~~java
var n1 = 7;                // int
var n2 = 7L;               // long
var n3 = Long.valueOf(7L); // Long
~~~

Cả ba hợp lệ nhưng mang những kiểu khác nhau.

## 4. Unboxing: wrapper trong phép toán số

Unboxing là chuyển giá trị của wrapper thành primitive tương ứng khi ngữ cảnh đòi giá trị primitive:

~~~java
Integer boxed = Integer.valueOf(7);
int primitive = boxed;       // unboxing Integer -> int
~~~

Với biểu thức số học:

~~~java
var boxed = Integer.valueOf(7); // Integer
var result = boxed + 2;         // int
~~~

Quá trình hiểu biểu thức `boxed + 2`:

1. Toán tử `+` đang là **cộng số học**.
2. `boxed` có kiểu `Integer` nên được **unbox** thành `int` để tham gia phép toán.
3. Literal `2` có kiểu `int`.
4. Phép cộng `int + int` cho kết quả kiểu `int`.
5. `var result` suy luận **`int`**, **không phải `Integer`**.

Đây là điểm quan trọng: **một initializer sử dụng wrapper không có nghĩa biến `var` luôn mang kiểu wrapper**. Kiểu cuối là kiểu của **toàn bộ biểu thức**.

~~~java
var a = Integer.valueOf(3); // Integer
var b = Integer.valueOf(4); // Integer
var sum = a + b;            // int: unbox cả hai rồi cộng
var product = a * b;        // int: unbox rồi nhân
var comparison = a < b;     // boolean: unbox để so sánh số
~~~

So sánh hai ngữ cảnh:

~~~java
var sameReferenceValue = a;  // Integer: copy giá trị tham chiếu, không cần phép cộng
var numericValue = a + 0;    // int: cộng số học buộc unboxing
~~~

Để chủ động lấy giá trị primitive, có thể gọi phương thức rõ ràng:

~~~java
var number = Integer.valueOf(12).intValue(); // int
~~~

### 4.1. Autoboxing/unboxing trong expression không phải phép biến đổi kiểu của biến

~~~java
var boxed = Integer.valueOf(5); // kiểu biên dịch: Integer
var plusOne = boxed + 1;        // kiểu biên dịch: int

boxed = Integer.valueOf(6);    // vẫn Integer
// boxed = 6.5;                // lỗi kiểu: double không gán được cho Integer
~~~

Với `var`, kiểu của biến được chốt từ initializer ban đầu. Các biểu thức tiếp theo có thể **unbox** giá trị khi cần nhưng không đổi định nghĩa kiểu của biến.

## 5. Chuyển đổi số và binary numeric promotion

Trong phép toán số học trên các giá trị primitive, Java có quy tắc **binary numeric promotion** để xác định kiểu tính toán chung. Khi một toán hạng là wrapper số hoặc `Character`, biểu thức có thể cần **unbox** trước khi áp dụng promotion.

Một mô hình dễ nhớ cho toán tử số học nhị phân `+`, `-`, `*`, `/`, `%` là:

1. Unbox toán hạng wrapper nếu cần.
2. Nếu có `double`, kết quả tính toán dùng `double`.
3. Nếu không có `double` nhưng có `float`, dùng `float`.
4. Nếu không có hai kiểu trên nhưng có `long`, dùng `long`.
5. Các trường hợp số nguyên còn lại được nâng lên `int`.

Đây là cách diễn đạt tóm tắt cho **numeric promotion** trong những phép toán số học nêu trên. Một số toán tử Java khác có quy tắc riêng (ví dụ toán tử dịch bit), nên không suy rộng bảng này sang mọi toán tử.

| Biểu thức | Kiểu của initializer | Vì sao |
| --- | --- | --- |
| `3 + 4` | `int` | `int + int`. |
| `3 + 4L` | `long` | Có toán hạng `long`. |
| `3 + 4.0f` | `float` | Có `float` và không có `double`. |
| `3 + 4.0` | `double` | Có `double`. |
| `3.0f + 4.0` | `double` | `double` ưu tiên hơn `float`. |
| `(byte) 3 + (short) 4` | `int` | `byte`/`short` đều được promote thành `int`. |
| `'A' + 1` | `int` | `char` tham gia số học được promote thành `int`. |
| `Integer.valueOf(3) + 4` | `int` | `Integer` unbox thành `int` rồi cộng. |
| `Long.valueOf(3L) + 4` | `long` | `Long` unbox thành `long` và `int` widen thành `long`. |

Vì vậy các biến sau mang kiểu khác nhau:

~~~java
var first = (byte) 3;          // byte
var second = (short) 4;        // short
var sum = first + second;      // int
var widened = second + 1L;    // long
~~~

**Không có quy tắc tự động trả kết quả `byte` chỉ vì cả hai toán hạng đều là `byte`.** Ngay cả `(byte) 3 + (byte) 4` cũng tạo biểu thức kiểu `int`.

### 5.1. Unary numeric promotion

Toán tử một ngôi như `+` và `-` cũng có quy tắc nâng kiểu số:

~~~java
var small = (byte) 3; // byte
var promoted = +small; // int
var negative = -small; // int
~~~

Biểu thức `+small` hoặc `-small` không giữ nguyên kiểu `byte`; kiểu kết quả là `int`. Với wrapper `Byte` hoặc `Short`, ngữ cảnh toán tử số có thể unbox rồi promote tương tự.

### 5.2. `char` và wrapper `Character` trong số học

~~~java
var letter = 'A'; // char
var numeric = letter + 1; // int: mã của 'A' là 65 => 66

var boxedLetter = Character.valueOf('A'); // Character
var nextCode = boxedLetter + 1;          // int: unboxing + promotion
~~~

Hai `var` ở vế trái đều suy luận từ **toàn bộ initializer**. `numeric` và `nextCode` có kiểu `int` chứ không phải `char` hoặc `Character`.

## 6. Widening, narrowing và vị trí đặt phép ép kiểu

**Widening primitive conversion** là chuyển từ kiểu có phạm vi biểu diễn hẹp hơn sang kiểu rộng hơn ở những cặp kiểu được Java cho phép, chẳng hạn `int` sang `long` hoặc `float` sang `double`. **Narrowing primitive conversion** đi theo chiều ngược lại, có thể mất phần thông tin; thường cần ép kiểu tường minh trong biểu thức.

~~~java
var small = 10;           // int
var wide = (long) small;  // long: cast xác định kiểu initializer
var fraction = (double) small; // double
~~~

Nếu muốn `var` suy luận kiểu cụ thể, đặt phép chuyển kiểu **ngay trong initializer**:

~~~java
var a = 10;        // int
var b = 10L;       // long
var c = (short) 10; // short
var d = (byte) 10;  // byte
~~~

Không phải mọi phép chuyển đổi đều bảo toàn giá trị:

~~~java
var narrowed = (byte) 128; // byte, giá trị -128
~~~

Ở đây `128` là số nguyên nằm ngoài khoảng biểu diễn của `byte`. Cast làm giá trị bị rút gọn theo quy tắc narrowing, **không** khiến `byte` lưu được giá trị 128.

### 6.1. Ép kiểu trước và sau phép toán cho kết quả khác nhau

~~~java
var early = (long) 2_000_000_000 + 1_000_000_000; // long, 3000000000
var late = (long) (2_000_000_000 + 1_000_000_000); // long, -1294967296
~~~

Trong `early`, một toán hạng đã là `long` **trước phép cộng**, nên phép toán được thực hiện ở `long`. Trong `late`, phép cộng `int + int` đã **tràn số** trước khi kết quả âm bị chuyển thành `long`.

Cách viết tự nhiên hơn khi biết cần `long`:

~~~java
var safe = 2_000_000_000L + 1_000_000_000; // long
~~~

**`var` không tự chọn `long` vì kết quả toán học “có vẻ quá lớn” cho `int`.** Nó suy luận đúng kiểu của biểu thức Java đã được biên dịch.

### 6.2. Cast kết quả và cast toán hạng khi cộng `byte`

~~~java
var sum = (byte) 127 + (byte) 1; // int, giá trị 128
var forced = (byte) ((byte) 127 + (byte) 1); // byte, giá trị -128
~~~

Ngay cả khi từng toán hạng là `byte`, phép cộng được thực hiện ở `int`. Chỉ cast cuối cùng mới biến kết quả thành `byte`, có thể mất dữ liệu. Dùng phép cast hẹp khi có lý do rõ ràng và chấp nhận được miền giá trị; nếu muốn báo lỗi thay vì tràn trong phép cộng số nguyên, xem xét `Math.addExact` với `int` hoặc `long`.

## 7. Chia nguyên và suy luận kiểu từ kết quả đã tính

~~~java
var quotient = 5 / 2;            // int, giá trị 2
var fraction = 5 / 2.0;         // double, giá trị 2.5
var earlyCast = (double) 5 / 2; // double, giá trị 2.5
var lateCast = (double) (5 / 2); // double, giá trị 2.0
~~~

- `5 / 2`: cả hai toán hạng là `int`. Java chia nguyên, bỏ phần thập phân bằng cách làm tròn về 0. Biến `quotient` có kiểu `int`.
- `5 / 2.0`: một toán hạng kiểu `double`; phép chia tính ở `double`. Biến `fraction` có kiểu `double`.
- `(double) 5 / 2`: ép toán hạng **trước phép chia**, nên vẫn giữ phần lẻ.
- `(double) (5 / 2)`: chia nguyên **xong mới ép**, không thể phục hồi phần lẻ đã mất.

Một trường hợp dễ nhầm với wrapper:

~~~java
var boxedFive = Integer.valueOf(5); // Integer
var ratio = boxedFive / 2;          // int, 2; unboxing rồi chia nguyên
var preciseRatio = boxedFive / 2.0; // double, 2.5
~~~

Không có “phép chia wrapper” trả về `Integer` ở đây; biểu thức unbox và áp dụng quy tắc toán tử số.

## 8. Điều kiện ba ngôi có thể dùng quy tắc chuyển đổi số

Toán tử điều kiện `condition ? expression1 : expression2` có quy tắc kiểu riêng. Nếu hai nhánh nằm trong một **numeric conditional expression**, kết quả có thể yêu cầu unboxing và numeric conversion.

Ví dụ:

~~~java
var numeric = true ? Integer.valueOf(7) : 0; // int
var nullable = true ? Integer.valueOf(7) : null; // Integer
~~~

Điểm khác biệt:

- `numeric`: nhánh `Integer` và nhánh literal `int` tạo một biểu thức điều kiện số; kiểu suy luận là `int`.
- `nullable`: nhánh wrapper và `null` là biểu thức điều kiện tham chiếu; kiểu là `Integer`, có thể nhận giá trị `null` nếu chọn nhánh đó.

Trong code thực tế, nếu một nhánh có thể thiếu giá trị, hãy cân nhắc giải quyết `null` rõ ràng trước khi làm toán để tránh unboxing không mong muốn.

## 9. Unboxing `null`: lỗi runtime cần phòng tránh

Wrapper có thể là `null`; primitive thì không. Nếu một phép toán cần unbox wrapper đang là `null`, chương trình ném **`NullPointerException`**.

~~~java
Integer missing = null;
// var total = missing + 1; // biên dịch được nhưng ném NPE khi chạy
~~~

`var` không bảo vệ khỏi lỗi này:

~~~java
var missing = (Integer) null; // hợp lệ: kiểu đã rõ là Integer
// var total = missing + 1;   // lỗi tại runtime khi unboxing
~~~

Cần phân biệt:

- `var missing = null;`: **lỗi biên dịch** vì `null` đơn lẻ không đủ kiểu để suy luận.
- `var missing = (Integer) null;`: **hợp lệ khi biên dịch**; biến có kiểu `Integer` và giá trị `null`.
- `var total = missing + 1;`: cú pháp/kiểu hợp lệ nếu `missing` là `Integer`, nhưng **ném `NullPointerException` khi thực thi** do unboxing `null`.

Các hướng xử lý phù hợp với nghiệp vụ:

~~~java
Integer maybeCount = null;

// Nếu nghiệp vụ cho phép mặc định là 0:
int count = maybeCount != null ? maybeCount : 0;

// Nếu thiếu giá trị phải báo lỗi rõ ràng:
int required = java.util.Objects.requireNonNull(
        maybeCount, "count is required");
~~~

Đây là đoạn minh họa; dòng `requireNonNull` sẽ ném lỗi có thông điệp nếu `maybeCount` vẫn là `null`. Không sử dụng mặc định 0 nếu 0 mang ý nghĩa khác “không có dữ liệu”. Với đầu vào từ JSON, database hoặc collection chứa wrapper, hãy xác định ngữ nghĩa vắng mặt trước khi áp dụng toán tử số.

## 10. Một số ngộ nhận liên quan đến `var`

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “`var number = 7` tạo `Integer` nhờ boxing.” | Literal `7` là `int`, nên `number` là `int`. |
| “Nếu initializer chứa `Integer` thì `var` chắc chắn là `Integer`.” | `var x = Integer.valueOf(7) + 1` là `int` do unboxing và cộng số. |
| “`byte + byte` có kiểu `byte`.” | Với phép cộng thông thường, cả hai được promote thành `int`. |
| “`Integer` có thể dùng an toàn mọi nơi như `int`.” | `Integer` có thể là `null`; unboxing có thể ném `NullPointerException`. |
| “Cast `long` sau phép cộng sẽ chữa tràn `int`.” | Khi phép cộng đã tràn, cast sau chỉ chuyển giá trị sai sang `long`. |
| “`var ratio = 5 / 2` tự thành `double` vì đó là phép chia.” | `int / int` cho `int`; kết quả là 2. |
| “Java tự nối widening + boxing cho mọi giá trị.” | Chuyển đổi phải tuân theo quy tắc ngữ cảnh; `Long value = 7;` không phải khai báo hợp lệ. |
| “`var` là kiểu động nên có thể đổi từ `Integer` sang `Double`.” | Kiểu của biến được suy luận **một lần khi biên dịch**, các phép gán sau phải tương thích. |
| “Wrapper là bất biến nên dùng `==` để so sánh số luôn đúng.” | `==` giữa hai tham chiếu wrapper kiểm tra đồng nhất đối tượng; dùng `equals` hoặc so sánh primitive sau khi kiểm soát `null` theo mục đích. |

## 11. Ví dụ Java 17+ hoàn chỉnh và kết quả dự đoán

Tạo file **`VarBoxingNumericDemo.java`**:

~~~java
public class VarBoxingNumericDemo {
    static String kind(int value) {
        return "int";
    }

    static String kind(long value) {
        return "long";
    }

    static String kind(double value) {
        return "double";
    }

    static String kind(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        Integer boxedViaAssignment = 7;       // automatic boxing
        var boxed = Integer.valueOf(7);       // Integer
        var sum = boxed + 2;                  // int
        var widened = boxed + 2L;             // long
        var promoted = (byte) 3 + (short) 4;  // int

        var divided = 5 / 2;                  // int: 2
        var fraction = 5 / 2.0;               // double: 2.5
        var tooLate = (double) (5 / 2);       // double: 2.0

        var overflow = 2_000_000_000 + 1_000_000_000;  // int overflow
        var safe = 2_000_000_000L + 1_000_000_000;     // long

        System.out.println("assignment wrapper=" + kind(boxedViaAssignment));
        System.out.println(
                "boxed=" + kind(boxed)
                + ", sum=" + kind(sum)
                + ", widened=" + kind(widened)
        );
        System.out.println("promoted=" + promoted + ", type=" + kind(promoted));
        System.out.println(
                "division=" + divided
                + ", fraction=" + fraction
                + ", castAfter=" + tooLate
        );
        System.out.println("overflow=" + overflow + ", safe=" + safe);

        var missing = (Integer) null;
        try {
            var invalid = missing + 1; // unboxing null
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: NullPointerException");
        }
    }
}
~~~

Chạy trong thư mục chứa file bằng một JDK 17 hoặc mới hơn:

~~~bash
javac VarBoxingNumericDemo.java
java VarBoxingNumericDemo
~~~

**Stdout dự kiến:**

~~~text
assignment wrapper=Integer
boxed=Integer, sum=int, widened=long
promoted=7, type=int
division=2, fraction=2.5, castAfter=2.0
overflow=-1294967296, safe=3000000000
null unboxing: NullPointerException
~~~

### Vì sao sử dụng các overload của `kind`?

Java chọn phương thức `kind(...)` phù hợp với **kiểu của biểu thức truyền vào**:

- `boxedViaAssignment` và `boxed` có kiểu `Integer` → overload `kind(Integer)`.
- `sum` và `promoted` có kiểu `int` → overload `kind(int)`.
- `widened` có kiểu `long` → overload `kind(long)`.

Nhờ vậy kết quả quan sát được **kiểu ở thời điểm biên dịch** thay vì đoán từ giá trị in ra. Ví dụ này kiểm chứng `var` tự suy luận kiểu sau các conversion thực sự xảy ra trong initializer.

### Vì sao overflow là `-1294967296`?

Phép cộng hai số `int` diễn ra với số học `int` 32 bit và không tự nới thành `long`. Tổng toán học là `3_000_000_000`, nằm ngoài miền `int`, nên giá trị `int` bị tràn về `-1_294_967_296`. Chỉ khi thêm `L` vào một toán hạng, phép cộng mới được thực hiện ở `long` và cho `3_000_000_000`.

### Vì sao dòng unboxing không làm chương trình dừng?

`missing` có kiểu `Integer` nhưng giá trị `null`. Biểu thức `missing + 1` cần primitive `int` nên unboxing ném `NullPointerException`. Khối `catch` bắt riêng ngoại lệ này và in thông điệp cố định, nên ví dụ vẫn hoàn thành.

## 12. Thực hành phân tích initializer mà không chạy code

Trước khi xem đáp án, hãy dự đoán kiểu của từng biến:

~~~java
var a = Byte.valueOf((byte) 4);
var b = a + 1;
var c = 1 + 2L;
var d = 1.0f + 2.0;
var e = Character.valueOf('A') + 1;
var f = (short) (4 + 5);
var g = (short) 4 + (short) 5;
var h = true ? Integer.valueOf(7) : 0;
var i = true ? Integer.valueOf(7) : null;
var j = Integer.parseInt("12");
var k = Integer.valueOf("12");
~~~

**Đáp án có giải thích:**

| Biến | Kiểu | Vì sao |
| --- | --- | --- |
| `a` | `Byte` | `Byte.valueOf(...)` trả wrapper. |
| `b` | `int` | `Byte` unbox thành `byte` rồi promote thành `int` để cộng với `1`. |
| `c` | `long` | `int + long` thực hiện ở `long`. |
| `d` | `double` | `float + double` thực hiện ở `double`. |
| `e` | `int` | `Character` unbox thành `char`, rồi promote thành `int`. |
| `f` | `short` | Cast áp dụng **sau** phép cộng. |
| `g` | `int` | Mỗi toán hạng `short` được promote thành `int` trước phép cộng. |
| `h` | `int` | Numeric conditional expression unbox wrapper và có kiểu `int`. |
| `i` | `Integer` | Nhánh wrapper và `null` tạo biểu thức điều kiện tham chiếu. |
| `j` | `int` | `Integer.parseInt` trả primitive. |
| `k` | `Integer` | `Integer.valueOf(String)` trả wrapper. |

Hãy tự thay `var` bằng tên kiểu dự đoán, sau đó biên dịch để kiểm tra. Khi một biểu thức không rõ, phân tích **từng toán hạng → chuyển đổi → loại toán tử → kiểu kết quả**, rồi mới suy luận kiểu của biến.

## 13. Áp dụng vào code thực tế

**Chọn primitive nếu chỉ tính toán số.** Ví dụ số lượng hàng, chỉ số, lần thử lại thường có thể dùng `int` hoặc `long`. `var` thích hợp khi initializer làm kiểu hiển nhiên:

~~~java
var retryCount = 3;  // int
var maxBytes = 1024L; // long
~~~

**Chỉ dùng wrapper khi có lý do rõ ràng.** Chẳng hạn generic collection, chữ ký API hoặc dữ liệu thiếu giá trị cần biểu diễn. Kiểm soát `null` trước khi dùng toán tử số; không giả định automatic unboxing luôn an toàn.

**Ghi rõ kiểu cho biểu thức số quan trọng.** Nếu logic đếm hoặc cộng có nguy cơ vượt `int`, dùng một toán hạng `long` **trước phép toán**. Nếu cần giữ phần thập phân, dùng `double` hoặc kiểu decimal phù hợp với nghiệp vụ trước khi chia. Với tiền tệ cần tính chính xác thập phân, cân nhắc `BigDecimal` được tạo từ chuỗi decimal hoặc nguồn số phù hợp, thay vì tin rằng `double` biểu diễn chính xác mọi phần mười.

**Không lạm dụng `var` để che mất kiểu quan trọng.** Ví dụ một phép tính trả về `double` dù dữ liệu mong muốn là `long` có thể khó phát hiện khi tên biến và biểu thức không rõ. Kiểu tường minh hoặc tên biến rõ nghĩa đôi lúc giúp đọc code tốt hơn.

**Đánh giá theo JDK và API hiện được hỗ trợ.** Những quy tắc trong bài không yêu cầu cài JDK 10; Java 17 và các bản JDK mới vẫn thực thi chúng. Không cần dùng API wrapper constructor đã lỗi thời để học boxing/unboxing.

## 14. Checklist tự kiểm tra

- [ ] Xác định được **kiểu chính xác của initializer**, thay vì đoán theo tên biến `var`.
- [ ] Phân biệt `var a = 7;` (**`int`**) và `var b = Integer.valueOf(7);` (**`Integer`**).
- [ ] Biết khi toán tử số cần **unbox** wrapper và khi nào có thể gặp `null`.
- [ ] Áp dụng **binary numeric promotion** theo `double → float → long → int` cho phép toán số học liên quan.
- [ ] Nhớ `byte`, `short`, `char` thường được promote thành `int` trong số học.
- [ ] Không cast **sau** phép cộng tràn số hay sau chia nguyên rồi mong khôi phục kết quả.
- [ ] Biết khi nào dùng literal `L`, `f`, `d` hoặc cast **trước** phép toán.
- [ ] Tránh dùng `==` để so sánh giá trị của hai reference wrapper khi mục tiêu là equality theo giá trị.
- [ ] Có thể đối chiếu kiểu bằng overload hoặc IDE/compiler thay vì nhìn riêng giá trị `println`.

## 15. Tài liệu chuẩn để đọc sâu hơn

- [JLS Java 25 `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): suy luận kiểu của khai báo biến cục bộ dùng `var`.
- [JLS Java 25 `5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): các chuyển đổi primitive sang wrapper.
- [JLS Java 25 `5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8): wrapper sang primitive và trường hợp `null`.
- [JLS Java 25 `5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.6): numeric promotion trong các phép toán.
- [JLS Java 25 `15.17 và `15.18 — Multiplicative/Additive Operators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html): phép chia, phép cộng, chuyển đổi kiểu toán hạng và kết quả.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): nền tảng ngữ nghĩa của `var` từ Java 10.

**Ghi nhớ:** `var` không tự boxing, unboxing, widening hay narrowing. **Chính biểu thức khởi tạo tuân theo các quy tắc chuyển đổi của Java**, và kiểu kết quả của biểu thức ấy mới là kiểu tĩnh mà `var` suy luận cho biến.