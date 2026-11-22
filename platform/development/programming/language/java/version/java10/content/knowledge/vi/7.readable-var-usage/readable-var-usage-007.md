# Nhận diện rủi ro chuyển đổi số khi thay bằng `var` (Java 10+)

## 1. Mục tiêu và nguyên tắc quan trọng nhất

Từ Java 10, `var` cho phép **suy luận kiểu của biến cục bộ tại thời điểm biên dịch**. Đây vẫn là tính năng Java hiện đại được sử dụng bình thường, không phải một cơ chế legacy hay một “kiểu động”.

Khi thay một khai báo có tên kiểu cụ thể bằng `var`, phải kiểm tra **kiểu tĩnh của initializer**, vì kiểu khai báo ban đầu có thể khác kiểu initializer do *assignment conversion*. Với dữ liệu số, khác biệt này ảnh hưởng đến:

1. Miền giá trị `int` so với `long` và nguy cơ **tràn số nguyên**.
2. Độ chính xác của `float` so với `double`.
3. Các kiểu hẹp `byte`, `short`, `char` so với `int`.
4. Phép chia số nguyên, numeric promotion, phép nhân/dịch bit.
5. Primitive so với wrapper, boxing/unboxing và lựa chọn phương thức overload.
6. Ngữ nghĩa toán tử điều kiện `?:` khi hai nhánh có kiểu số khác nhau.

**Điểm mấu chốt:** compiler xác định kiểu của `var x = initializer;` từ **kiểu biểu thức `initializer`**, không từ kiểu cũ đã xóa, không từ mong muốn của người viết và không từ giá trị thực tế lúc chạy.

```java
long oldValue = 7; // oldValue có kiểu long
var newValue = 7;  // newValue có kiểu int
var fixed = 7L;    // fixed có kiểu long
```

Giá trị của ba biến lúc khởi tạo đều là 7, nhưng toán tử và lời gọi phương thức về sau có thể đối xử khác nhau với `int` và `long`. Vì vậy thay `long` bằng `var` không đơn thuần là rút gọn cú pháp nếu initializer vẫn là literal `int`.

## 2. Ba tầng cần tách khi phân tích lỗi

Đối với một câu lệnh như `long total = a + b;`, cần phân biệt:

- **Kiểu toán hạng:** kiểu của `a` và `b`.
- **Kiểu biểu thức:** kiểu của `a + b` sau khi áp dụng quy tắc numeric promotion.
- **Kiểu biến đích:** `long`; Java có thể thực hiện chuyển đổi khi gán kết quả vào biến.

Chẳng hạn:

```java
int a = 1_500_000_000;
int b = 1_500_000_000;

long result = a + b; // Tràn int TRƯỚC khi nới rộng sang long
```

Phép cộng `a + b` được thực hiện bằng `int` vì hai toán hạng đều là `int`. Kết quả tràn thành `-1294967296` rồi mới được chuyển thành `long`. Viết `var result = a + b;` làm biến đích có kiểu `int`, nhưng **lỗi tràn trong biểu thức đã tồn tại ngay cả khi khai báo `long`**.

Để sửa, phải thay đổi **kiểu phép toán trước khi tính**:

```java
var correct = (long) a + b; // long + int -> long: 3000000000
// Hoặc:
long alsoCorrect = (long) a + b;
```

Điều này minh họa cách review đúng: phân biệt “lỗi có sẵn trong biểu thức” với “hệ quả mới do kiểu biến thay đổi sau khi dùng `var`”.

## 3. Bảng refactor: ví dụ nào thay đổi kiểu?

Mỗi hàng trong bảng là một ví dụ độc lập, không phải các câu lệnh khai báo lặp tên trong cùng phương thức.

| Khai báo trước | Thay trực tiếp bằng `var` | Kiểu cũ → kiểu mới | Điều cần cảnh giác |
| --- | --- | --- | --- |
| `long n = 7;` | `var n = 7;` | `long` → `int` | Miền giá trị của phép toán về sau bị thu hẹp |
| `byte n = 7;` | `var n = 7;` | `byte` → `int` | Overload `byte` khác `int` |
| `short n = 7;` | `var n = 7;` | `short` → `int` | Mất thông tin kiểu nhỏ trong API |
| `char n = 65;` | `var n = 65;` | `char` → `int` | Hiển thị ký tự khác hiển thị số |
| `float n = 1;` | `var n = 1;` | `float` → `int` | Phép tính sau có thể dùng chia nguyên |
| `double n = 1.5f;` | `var n = 1.5f;` | `double` → `float` | Độ chính xác/phương thức overload thay đổi |
| `Long n = 9L;` | `var n = 9L;` | `Long` → `long` | Mất tính nullable của wrapper |
| `Integer n = 9;` | `var n = 9;` | `Integer` → `int` | Boxing/overload khác |
| `double n = 5 / 2;` | `var n = 5 / 2;` | `double` → `int` | **Phép chia vẫn là chia nguyên trong cả hai trường hợp** |
| `long n = 9L;` | `var n = 9L;` | Không đổi: `long` | Thay thế tương đương về kiểu biến |

Không phải mọi `var` đều nguy hiểm. Một cuộc refactor tốt là cuộc refactor **biết chính xác kiểu sau khi suy luận** và đã kiểm tra việc sử dụng biến đó ở các dòng tiếp theo.

## 4. Literal: một ký tự hậu tố có thể quyết định cả kiểu

Các literal số quen thuộc có kiểu tĩnh theo cú pháp:

| Literal | Kiểu |
| --- | --- |
| `1`, `1_000`, `0xFF` | `int` nếu literal hợp lệ trong miền quy định |
| `1L`, `1l` | `long`, nên viết `L` hoa |
| `1.0`, `1.0d` | `double` |
| `1.0f`, `1.0F` | `float` |
| `'A'` | `char`, khác số nguyên `65` |

```java
var integer = 1;          // int
var longValue = 1L;       // long
var real = 1.0;           // double
var floatValue = 1.0f;    // float
var letter = 'A';         // char
var capacity = 3_000_000_000L; // long
```

Không thể sửa một literal thập phân quá lớn bằng cách chỉ ghi `var`:

```java
// var wrong = 3_000_000_000;  // Lỗi biên dịch: decimal integer literal vượt int
var correct = 3_000_000_000L; // long
```

Tương tự, `var rate = 0.5;` là `double`, không phải `float`. Nếu một API thật sự yêu cầu `float`, dùng `0.5f` hoặc kiểu tường minh thích hợp.

Lưu ý: một biểu thức có literal `int` không nhất thiết cho kết quả kiểu `int` nếu có toán hạng khác kiểu `long`/`double`. Cần xét **toàn biểu thức**, không chỉ literal đầu tiên.

## 5. Rủi ro số nguyên lớn: lỗi mới sau khi đổi kiểu biến

So sánh:

```java
long capacity = 1_500_000_000; // long
var requested = 1_500_000_000; // int

System.out.println(capacity + capacity);   // 3000000000
System.out.println(requested + requested); // -1294967296
```

Cùng giá trị khởi tạo 1,5 tỷ nhưng phép cộng xảy ra trong hai miền kiểu khác nhau:

- `long + long` được tính trong 64 bit, có thể biểu diễn 3 tỷ.
- `int + int` được tính trong 32 bit, vượt `Integer.MAX_VALUE` và wrap-around.

Đây là **bug thực sự có thể sinh ra từ việc thay khai báo `long` bằng `var`** mà không đổi literal. Cách sửa:

```java
var requested = 1_500_000_000L; // long từ initializer
var total = requested + requested;
System.out.println(total); // 3000000000
```

Hoặc giữ kiểu `long` tường minh nếu đó là hợp đồng của dữ liệu (kích thước file, thời gian, tổng số lượng, số tiền tính theo đơn vị nguyên...).

### Tràn trước khi gán vào `long`: lỗi vốn có

```java
long stillWrong = 1_500_000_000 + 1_500_000_000;
// Giá trị vẫn là -1294967296: phép cộng int đã tràn
```

Dù biến đích là `long`, không có phép “tính lại” trong 64 bit. Sửa từ nguồn:

```java
var correct1 = 1_500_000_000L + 1_500_000_000;
var correct2 = (long) 1_500_000_000 + 1_500_000_000;
System.out.println(correct1); // 3000000000
System.out.println(correct2); // 3000000000
```

Đặt cast ngoài toàn bộ phép tính **không đủ**:

```java
var tooLate = (long) (1_500_000_000 + 1_500_000_000);
// Kết quả là long nhưng vẫn chứa -1294967296.
```

### Rủi ro khi nhân

```java
int units = 80_000;
int unitPrice = 40_000;

long wrong = units * unitPrice; // int * int: overflow trước khi gán long
var correct = (long) units * unitPrice; // long * int
System.out.println(correct); // 3200000000
```

Nếu miền giá trị có thể vượt `long`, hãy dùng kiểu số tùy ý `BigInteger` hoặc cách tính được kiểm soát; `var` không tăng miền số.

## 6. Rủi ro ở chia số nguyên: đừng quy lỗi nhầm cho `var`

```java
double oldResult = 5 / 2; // double 2.0
var newResult = 5 / 2;    // int 2
var accurate = 5.0 / 2;   // double 2.5
```

Phép `5 / 2` được đánh giá bằng `int`, nên kết quả **luôn là 2**, sau đó biến `double oldResult` được gán giá trị `2.0` thông qua widening. `var` giữ kiểu `int` của initializer; nó không tự tạo ra chia nguyên.

Sửa ý định tính trung bình:

```java
int total = 5;
int count = 2;

var average = total / (double) count;
System.out.println(average); // 2.5
```

Khi một số cần được tính theo số thực, ít nhất một toán hạng trong phép chia phải có kiểu số thực phù hợp. Nếu `count` có thể bằng 0, cần kiểm tra riêng theo quy tắc ứng dụng; chia `double` cho số 0 có thể cho Infinity/NaN thay vì ngoại lệ của phép chia nguyên.

Với mã cũ `double average = total / count;`, lỗi chia nguyên đã tồn tại **trước khi dùng `var`**. Vì thế review phải ghi rõ: thay đổi kiểu biến có thể làm thay đổi hành vi sau đó; còn phép chia sai là lỗi biểu thức cần được sửa độc lập.

## 7. Rủi ro khi mất `byte`/`short`/`char`

Các khai báo sau hợp lệ do Java cho phép *narrowing* một **hằng số nguyên phù hợp miền giá trị** tại ngữ cảnh gán:

```java
byte level = 7;
short index = 100;
char symbol = 65; // ký tự 'A'
```

Nhưng:

```java
var level = 7;  // int
var index = 100; // int
var symbol = 65; // int, không phải char
```

Hệ quả: lời gọi overload khác, phương thức đòi `byte`/`short`/`char` có thể không chấp nhận `int`, và `System.out.println(symbol)` sẽ in `65` chứ không in `A`.

Nếu kiểu hẹp là thông tin quan trọng, **giữ khai báo kiểu tường minh**. Hoặc với trường hợp bắt buộc:

```java
var small = (byte) 7; // byte
var letter = (char) 65; // char
```

Nhưng ép kiểu hẹp có thể mất dữ liệu với giá trị ngoài miền; không nên thêm cast tùy tiện để chỉ làm cú pháp có `var`.

### Phép toán số học có thể tự nâng `byte` lên `int`

```java
byte left = 10;
byte right = 20;
var total = left + right; // int
```

Đây là **binary numeric promotion**. Dù hai toán hạng kiểu `byte`, biểu thức cộng có kiểu `int`. Không thể cho rằng `var` luôn giữ nguyên kiểu của toán hạng đầu tiên.

## 8. Rủi ro `float`/`double` và độ chính xác

```java
double oldRate = 1.5f; // float literal được widening thành double
var newRate = 1.5f;    // float
```

Dù giá trị ban đầu giống nhau trong trường hợp này, phép tính tiếp theo có thể được thực hiện với độ chính xác và cách làm tròn khác vì `oldRate` có kiểu `double`, còn `newRate` có kiểu `float`.

Muốn giữ `double` khi dùng `var`, cung cấp initializer kiểu `double`:

```java
var rate = 1.5;  // double
var otherRate = (double) 1.5f; // double, sau chuyển từ float
```

Không nhầm **widening `float` thành `double`** với việc khôi phục chính xác thập phân; nếu literal đã được làm tròn ở độ chính xác `float` thì chuyển sang `double` không khôi phục các bit thông tin đã mất.

Cả `float` và `double` đều là số thực nhị phân, nên:

```java
var sum = 0.1 + 0.2; 
System.out.println(sum); // 0.30000000000000004
```

Nếu bài toán tiền tệ thực sự yêu cầu phép tính thập phân chính xác, chọn `BigDecimal` và nguồn dữ liệu phù hợp:

```java
var tenCents = new java.math.BigDecimal("0.1");
var twentyCents = new java.math.BigDecimal("0.2");
var exact = tenCents.add(twentyCents);
System.out.println(exact); // 0.3
```

`var` trong ví dụ chỉ suy luận `BigDecimal`; chính kiểu dữ liệu và cách tạo số quyết định độ chính xác, không phải chữ `var`.

## 9. Rủi ro boxing/unboxing: `Long` không đồng nghĩa `long`

```java
Long oldId = 9L;           // Long: wrapper do boxing
var newId = 9L;            // long: primitive
var keptWrapper = Long.valueOf(9L); // Long
```

Giá trị khởi tạo đều là 9, nhưng:

- `oldId` có thể là `null`; `newId` không.
- Phương thức instance của wrapper có thể được gọi trên `oldId` khi không null; `newId` là primitive nên không có các phương thức instance.
- Overload `f(long)` và `f(Long)` có thể được compiler chọn khác nhau.
- Khi truyền qua API generic/collection có thể xảy ra boxing, nhưng `newId` không vì thế đổi kiểu biến thành `Long`.

Đoạn sau minh họa overload, cần đặt trong class có hai phương thức `kind` tương ứng:

```java
static String kind(long n) { return "long"; }
static String kind(Long n) { return "Long"; }

// Bên trong main:
Long first = 9L;
var second = 9L;
System.out.println(kind(first));  // Long
System.out.println(kind(second)); // long
```

Với `Integer` và `int` cũng phải phân biệt. Nếu initializer bản thân đã có kiểu wrapper, `var` vẫn giữ wrapper:

```java
Integer nullable = null;
var copy = nullable; // Integer, không phải int
```

Tại khai báo trên không có unboxing. Nếu sau đó dùng `copy` trong biểu thức bắt buộc primitive, unboxing giá trị `null` mới có thể gây `NullPointerException`. Không nên cho rằng mọi `var` đều suy luận primitive hoặc mọi `var` đều tránh lỗi `null`.

## 10. Rủi ro khi dùng operator và toán tử điều kiện

Theo quy tắc numeric promotion, kiểu kết quả có thể khác từng toán hạng:

```java
var x = 1 + 2L;  // long
var y = 1 + 2.0; // double
var z = 5 / 2;   // int

byte small = 1;
var promoted = small + small; // int
```

Với `?:`, compiler xét cả hai nhánh:

```java
boolean condition = true;
var mixed = condition ? 1 : 2L; // long
```

Cho dù lúc chạy chọn nhánh `1`, biến `mixed` có kiểu `long` vì biểu thức điều kiện số được xác định kiểu từ cả hai nhánh. Có các quy tắc riêng cho numeric conditional có kiểu hẹp hoặc wrapper; không dùng công thức đơn giản “lấy loại rộng nhất” thay thế toàn bộ đặc tả JLS.

### Rủi ro dịch bit

```java
long wrong = 1 << 35;  // 8, vì toán hạng trái kiểu int
var correct = 1L << 35; // long 34359738368
```

Với `int`, khoảng dịch `35` được giới hạn bằng 5 bit thấp (thành 3); phép dịch tính như `int` rồi kết quả 8 mới được widening vào `long wrong`. Với `1L`, toán hạng trái `long` khiến phép dịch thực hiện trên 64 bit. Đây lại là trường hợp mà **kiểu toán hạng quan trọng hơn kiểu biến đích**.

Đừng quên rằng việc thay kiểu tường minh bằng `var` còn có thể ảnh hưởng đến cách những biểu thức **sử dụng biến sau đó** được tính, ngay cả nếu biểu thức initializer không gây lỗi.

## 11. Ví dụ Java 10+ hoàn chỉnh, có kết quả chạy đã kiểm tra

Tạo tệp **`VarNumericDemo.java`**:

```java
public final class VarNumericDemo {
    static String kind(byte value) { return "byte"; }
    static String kind(int value) { return "int"; }
    static String kind(long value) { return "long"; }
    static String kind(Long value) { return "Long"; }
    static String kind(float value) { return "float"; }
    static String kind(double value) { return "double"; }

    public static void main(String[] args) {
        long declaredLong = 7;
        var inferredInt = 7;
        System.out.println("long vs var: " + kind(declaredLong) + " / " + kind(inferredInt));

        byte declaredByte = 7;
        var inferredAnotherInt = 7;
        System.out.println("byte vs var: " + kind(declaredByte) + " / " + kind(inferredAnotherInt));

        Long declaredBox = 9L;
        var inferredPrimitive = 9L;
        System.out.println("Long vs var: " + kind(declaredBox) + " / " + kind(inferredPrimitive));

        double declaredDouble = 1.5f;
        var inferredFloat = 1.5f;
        System.out.println("double vs var: " + kind(declaredDouble) + " / " + kind(inferredFloat));

        long wide = 1_500_000_000;
        var narrow = 1_500_000_000;
        System.out.println("wide sum=" + (wide + wide));
        System.out.println("var sum=" + (narrow + narrow));

        long tooLate = 1_500_000_000 + 1_500_000_000;
        var right = 1_500_000_000L + 1_500_000_000;
        System.out.println("late widening=" + tooLate);
        System.out.println("long arithmetic=" + right);

        double dividedDouble = 5 / 2;
        var dividedInt = 5 / 2;
        var fractional = 5.0 / 2;
        System.out.println("division=" + dividedDouble + " / " + dividedInt + " / " + fractional);

        boolean preferLong = true;
        var mixedNumber = preferLong ? 1 : 2L;
        System.out.println("conditional type=" + kind(mixedNumber));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("unexpected");
        } catch (ArithmeticException overflow) {
            System.out.println("addExact=overflow");
        }
    }
}
```

Biên dịch bằng một JDK hỗ trợ `--release 10` rồi chạy:

```bash
javac --release 10 VarNumericDemo.java
java VarNumericDemo
```

Kết quả stdout **chính xác**:

```text
long vs var: long / int
byte vs var: byte / int
Long vs var: Long / long
double vs var: double / float
wide sum=3000000000
var sum=-1294967296
late widening=-1294967296
long arithmetic=3000000000
division=2.0 / 2 / 2.5
conditional type=long
addExact=overflow
```

Diễn giải kết quả:

1. Bốn dòng đầu cho thấy **kiểu tĩnh đã đổi** khi xóa tên kiểu ở vế trái. Compiler chọn overload theo kiểu biến, không theo giá trị số giống nhau.
2. `wide sum` và `var sum` khác vì `long + long` không tràn ở 3 tỷ, còn `int + int` tràn.
3. `late widening` chứng minh lỗi `int` overflow đã có ngay cả với biến đích `long`; `long arithmetic` nới rộng một toán hạng trước phép cộng.
4. `division` phân biệt `double 2.0`, `int 2` và `double 2.5`.
5. `conditional type` xác nhận quy tắc numeric conditional giữa `int` và `long`.
6. `Math.addExact(int,int)` ném `ArithmeticException` khi overflow thay vì âm thầm wrap-around.

Ví dụ không phụ thuộc thư viện bên thứ ba và dùng API Java SE vẫn được hỗ trợ.

## 12. Kiểm soát tràn bằng API phù hợp

`var` không có cơ chế tự phát hiện overflow. Với phép tính bắt buộc báo lỗi khi vượt miền giá trị, dùng các API `Math.*Exact` theo **kiểu toán hạng phù hợp**:

```java
int count = Integer.MAX_VALUE;

try {
    var sum = Math.addExact(count, 1);
    System.out.println(sum);
} catch (ArithmeticException exception) {
    System.out.println("overflow");
}
```

Cũng có các phương thức như `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.decrementExact` và `Math.toIntExact`. Dùng overload `int` hoặc `long` tùy miền giá trị phải bảo vệ.

Ví dụ có thể kiểm tra tràn `long`:

```java
long maximum = Long.MAX_VALUE;
try {
    var next = Math.addExact(maximum, 1L);
    System.out.println(next);
} catch (ArithmeticException ex) {
    System.out.println("overflow");
}
```

Nhưng `Math.addExact(a + b, c)` vẫn có thể để `a + b` overflow **trước khi gọi phương thức** nếu `a, b` đều là `int`. Phải thiết kế phép tính để từng bước được kiểm tra hoặc sử dụng kiểu toán hạng đủ lớn ngay từ đầu.

Nếu yêu cầu miền số vượt cả `long`, sử dụng `BigInteger`:

```java
var maximum = new java.math.BigInteger("9223372036854775807");
var beyondLong = maximum.add(java.math.BigInteger.ONE);
System.out.println(beyondLong); // 9223372036854775808
```

`BigInteger` là lựa chọn mô hình dữ liệu, không phải kết quả tự động của việc viết `var`.

## 13. Quy trình review trước khi thay bằng `var`

**Bước 1: ghi lại kiểu cũ.** `long`, `double`, `byte`, `Long` có ý nghĩa khác nhau. Khi kiểu cũ thể hiện hợp đồng nghiệp vụ, giữ kiểu tường minh có thể là phương án tốt nhất.

**Bước 2: suy luận kiểu initializer.** Xem literal suffix `L`, `f`, cast, kiểu trả về phương thức và numeric promotion. Compiler suy luận kiểu từ **toàn bộ biểu thức**, không phải từ giá trị ở nhánh đang chạy.

**Bước 3: so sánh kiểu trước–sau.** Kiểm tra widening primitive, constant narrowing, boxing/unboxing có đang dựa vào kiểu bên trái cũ hay không. Nếu có, `var` có thể thay đổi kiểu đích thực sự.

**Bước 4: rà soát toàn bộ việc sử dụng biến.** Tìm phép cộng/nhân, chia, dịch bit, ép kiểu, gán lại giá trị lớn hơn, overload, API generic, khả năng null và serialize. Rủi ro thường nằm ở **dòng dùng biến tiếp theo**, không phải khai báo ban đầu.

**Bước 5: thử ranh giới.** Test gần `Integer.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE`, các phép chia, số âm, 0, wrapper null và số thực nhị phân. Chỉ dùng ví dụ nhỏ không đủ để đảm bảo refactor an toàn.

**Bước 6: sửa chủ đích, không refactor hàng loạt.** Nếu cần `long`, dùng literal `L` hoặc toán hạng `long` **trước khi tính**, hoặc giữ `long` tường minh. Nếu cần `byte/short/char` hoặc nullable wrapper, giữ kiểu đích có thể dễ đọc hơn thêm cast/constructor chỉ để dùng `var`.

Checklist:

- [ ] Kiểu suy luận mới khớp hợp đồng kiểu cũ, hoặc khác biệt đã được chủ động xử lý.
- [ ] Mọi phép toán số nguyên quan trọng chạy trong miền đủ lớn **trước khi nhận kết quả**.
- [ ] Phép chia nguyên hay thực là lựa chọn có chủ đích.
- [ ] Primitive/wrapper và phương thức overload không thay đổi ngoài ý muốn.
- [ ] Kiểu hẹp và thao tác ký tự vẫn đúng với API cần gọi.
- [ ] Floating-point precision phù hợp với nghiệp vụ; số tiền decimal được xử lý bằng mô hình dữ liệu phù hợp.
- [ ] Có test giá trị biên và test hành vi chương trình.

## 14. Các lỗi phổ biến cần tránh

### 14.1. “Cùng giá trị đầu nên cùng kiểu”

Sai. `long n = 7;` và `var n = 7;` cùng chứa số 7 nhưng không cùng kiểu; phép cộng, overload và miền giá trị sau đó có thể khác.

### 14.2. “Khai báo `long` sẽ tự làm biểu thức cộng `int` an toàn”

Sai. `long result = a + b;` với `a, b` kiểu `int` có thể đã tràn trước phép gán. Dùng `(long) a + b` hoặc kiểm tra từng phép tính.

### 14.3. “Gán vào `double` biến chia nguyên thành chia thực”

Sai. `double result = 5 / 2;` nhận `2.0`, không phải `2.5`. Cần thay toán hạng trước khi chia.

### 14.4. “Thay `Long` bằng `var` không làm thay đổi API”

Có thể sai. `Long x = 1L;` khai báo wrapper, `var x = 1L;` khai báo primitive `long`. Null, method selection và những thao tác trên object khác nhau.

### 14.5. “`var` chọn kiểu của nhánh được thực thi trong toán tử `?:`”

Sai. Kiểu được compiler xác định từ cả biểu thức, chẳng hạn `var x = true ? 1 : 2L;` là `long`.

### 14.6. “Chỉ cần ép kiểu sau khi tính là hết overflow”

Sai. `(long) (a * b)` với `a,b` kiểu `int` không cứu kết quả `int` đã tràn. Phải nới rộng một toán hạng **trước phép nhân**.

### 14.7. “Thay kiểu tường minh bằng `var` luôn giúp mã dễ đọc hơn”

Không phải lúc nào cũng vậy. Khi kiểu số là một phần hợp đồng nghiệp vụ, `long totalBytes`, `double probability` hoặc `Long optionalId` thường rõ hơn `var` mà initializer không đủ biểu đạt ý định.

## 15. Câu hỏi tự kiểm tra

**1.** `long x = 1;` và `var x = 1;` có cùng kiểu không?

**Đáp án:** Không. Câu thứ nhất là `long`, câu thứ hai `int`. Muốn `var` giữ `long`, dùng `1L`.

**2.** Vì sao `long total = 2_000_000_000 + 200_000_000;` có thể sai?

**Đáp án:** Hai toán hạng là `int`, phép cộng vượt miền `int` trước khi chuyển sang `long`. Cần `2_000_000_000L + 200_000_000` hoặc cast một toán hạng trước khi cộng.

**3.** `var x = 5 / 2;` là kiểu gì? `double y = 5 / 2;` có bằng 2.5 không?

**Đáp án:** `x` là `int` với giá trị 2. `y` là `double 2.0`; phép chia đã là chia nguyên trước widening. Muốn 2.5, dùng `5.0 / 2`.

**4.** `byte b = 7;` có thể được thay bằng `var b = 7;` mà không đổi kiểu không?

**Đáp án:** Không; `var` suy luận `int`. Java cho phép narrowing hằng nguyên phù hợp vào `byte` trong khai báo ban đầu, nhưng không áp đặt `byte` cho initializer `var`.

**5.** `Long id = 2L;` so với `var id = 2L;` khác gì?

**Đáp án:** Khai báo đầu dùng wrapper `Long` và có thể nhận `null`; khai báo sau dùng primitive `long`. Muốn giữ wrapper, có thể dùng `var id = Long.valueOf(2L);`.

**6.** `var x = true ? 1 : 2L;` có kiểu nào?

**Đáp án:** `long`, vì numeric conditional xét cả hai nhánh, không chỉ nhánh đang được chọn.

**7.** Vì sao `long mask = 1 << 35;` cho giá trị khác `var mask = 1L << 35;`?

**Đáp án:** Vế trái `int` khiến phép dịch dùng khoảng cách 5 bit thấp, dẫn tới `1 << 35 == 8`. Với `1L`, phép dịch trong 64 bit, giá trị bằng `34359738368`.

**8.** `var result = (long) (a * b);` với `a,b` đều là `int` đã đảm bảo không tràn chưa?

**Đáp án:** Chưa, phép nhân `int` vẫn có thể tràn trước cast. Dùng `var result = (long) a * b;` nếu miền `long` đủ lớn, hoặc kiểm tra tràn theo hợp đồng.

## Tài liệu chính thức, còn áp dụng trong Java hiện đại

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): quy tắc suy luận kiểu `var` được giới thiệu từ Java 10.
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): cách bảo đảm kiểu và ý định vẫn rõ ràng khi dùng `var`.
- [Java Language Specification — Assignment Contexts, mục 5.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2): widening, boxing và constant narrowing.
- [Java Language Specification — Numeric Contexts, mục 5.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.6): quy tắc unary/binary numeric promotion.
- [Java Language Specification — Multiplicative Operators, mục 15.17](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.17): nhân và chia.
- [Java Language Specification — Conditional Operator, mục 15.25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25): kiểu kết quả toán tử `?:`.
- [Java SE Math API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact` và các phép kiểm tra tràn số nguyên.
