# Toán tử dấu `+`, dấu `-` và phủ định `!` — Java 17+

Trong Java, `+`, `-` và `!` là **toán tử một ngôi** (*unary operators*) khi được đặt trước **một** toán hạng. Chúng cần được phân biệt với phép cộng/trừ hai ngôi.

~~~java
int number = 7;
int positive = +number;   // 7.
int negative = -number;   // -7.
boolean online = true;
boolean offline = !online; // false.
~~~

`+x` giữ giá trị số sau khi áp dụng **unary numeric promotion**; `-x` đổi dấu giá trị số; `!condition` đảo giá trị boolean. Chúng **không tự thay đổi biến nguồn** (khác với `++x`, `x++` hoặc `--x`).

## 1. Nhận biết ba toán tử

| Biểu thức | Tên | Kiểu toán hạng hợp lệ | Kết quả |
| --- | --- | --- | --- |
| `+x` | Dấu cộng một ngôi | Primitive số hoặc wrapper số được unbox | Giá trị số sau nâng kiểu |
| `-x` | Dấu trừ một ngôi | Primitive số hoặc wrapper số được unbox | Giá trị đổi dấu sau nâng kiểu |
| `!x` | Phủ định logic | `boolean` hoặc `Boolean` được unbox | Giá trị `boolean` ngược lại |

Ví dụ, `+5` không phải phép cộng hai toán hạng, còn `5 + 2` mới là phép cộng hai ngôi. Tương tự, `-5` là dấu trừ một ngôi nhưng `5 - 2` là phép trừ hai ngôi. `!` không dùng được với `int`, `double`, `String` hoặc đối tượng bất kỳ nếu đối tượng đó không được unbox thành `boolean`.

## 2. Chương trình Java 17+ độc lập

Tạo file UTF-8 **`UnarySignsAndNotDemo.java`**:

~~~java
public class UnarySignsAndNotDemo {
    static String typeOf(int unused) {
        return "int";
    }

    static String typeOf(long unused) {
        return "long";
    }

    static String typeOf(double unused) {
        return "double";
    }

    public static void main(String[] args) {
        int number = 7;
        System.out.println("unaryPlus=" + (+number));
        System.out.println("unaryMinus=" + (-number));
        System.out.println("binaryPlus=" + (10 + number));
        System.out.println("binaryMinus=" + (10 - number));
        System.out.println("originalNumber=" + number);

        byte small = 5;
        short medium = 6;
        char letter = 'A';
        long large = 7L;
        double fraction = 2.5;

        System.out.println("plusByteType=" + typeOf(+small));
        System.out.println("minusShortType=" + typeOf(-medium));
        System.out.println("plusCharType=" + typeOf(+letter));
        System.out.println("plusCharValue=" + (+letter));
        System.out.println("plusLongType=" + typeOf(+large));
        System.out.println("minusDoubleType=" + typeOf(-fraction));
        System.out.println("minusDoubleValue=" + (-fraction));

        Integer boxedNumber = 8;
        Boolean boxedFalse = Boolean.FALSE;
        System.out.println("boxedMinusType=" + typeOf(-boxedNumber));
        System.out.println("boxedMinusValue=" + (-boxedNumber));
        System.out.println("boxedNot=" + (!boxedFalse));

        boolean ready = true;
        boolean enabled = false;
        System.out.println("notReady=" + (!ready));
        System.out.println("doubleNot=" + (!!ready));
        System.out.println("groupedNot=" + (!(ready && enabled)));
        System.out.println("notComparison=" + (!(number > 10)));
        System.out.println("deMorgan="
                + ((!(ready && enabled))
                        == ((!ready) || (!enabled))));

        int minimum = Integer.MIN_VALUE;
        System.out.println("minNegatedInt=" + (-minimum));
        System.out.println("minNegatedAsLong=" + (-(long) minimum));
        try {
            Math.negateExact(minimum);
            System.out.println("unexpected=no-error");
        } catch (ArithmeticException ex) {
            System.out.println("negateExact=ArithmeticException");
        }

        double negativeZero = -0.0;
        System.out.println("negativeZero=" + negativeZero);
        System.out.println("zerosEqual=" + (negativeZero == +0.0));
        System.out.println("negativeZeroReciprocal=" + (1.0 / negativeZero));

        double notANumber = Double.NaN;
        System.out.println("notNaNEquality="
                + (!(notANumber == notANumber)));

        Integer missingNumber = null;
        try {
            int unused = -missingNumber;
            System.out.println("unexpectedNumber=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullNumber=NullPointerException");
        }

        Boolean missingFlag = null;
        try {
            boolean unused = !missingFlag;
            System.out.println("unexpectedFlag=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullBoolean=NullPointerException");
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên, tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 UnarySignsAndNotDemo.java
java UnarySignsAndNotDemo
~~~

**Expected stdout chính xác** của lệnh `java UnarySignsAndNotDemo` (không bao gồm đầu ra phiên bản JDK):

~~~text
unaryPlus=7
unaryMinus=-7
binaryPlus=17
binaryMinus=3
originalNumber=7
plusByteType=int
minusShortType=int
plusCharType=int
plusCharValue=65
plusLongType=long
minusDoubleType=double
minusDoubleValue=-2.5
boxedMinusType=int
boxedMinusValue=-8
boxedNot=true
notReady=false
doubleNot=true
groupedNot=true
notComparison=true
deMorgan=true
minNegatedInt=-2147483648
minNegatedAsLong=2147483648
negateExact=ArithmeticException
negativeZero=-0.0
zerosEqual=true
negativeZeroReciprocal=-Infinity
notNaNEquality=true
nullNumber=NullPointerException
nullBoolean=NullPointerException
~~~

Các overload `typeOf(int)`, `typeOf(long)`, `typeOf(double)` biểu thị **kiểu tĩnh của biểu thức tại compile time**. Chúng giúp chứng minh `+small` có kiểu `int`, không còn kiểu `byte`. Code đã chủ động bắt các ngoại lệ được minh họa để giữ stdout ổn định.

## 3. Dấu cộng `+` một ngôi và toán tử `+` hai ngôi

~~~java
int n = 4;
int unchanged = +n; // 4.
int total = n + 5;   // 9.
~~~

- `+n` chỉ có một toán hạng số, không tự tăng `n`.
- `n + 5` có hai toán hạng và thực hiện phép cộng.
- `"count=" + n` là `+` hai ngôi **nối chuỗi** vì có toán hạng `String`.

`+` một ngôi **không** đọc chuỗi rồi phân tích thành số:

~~~java
// int invalid = +"42";  // Loi bien dich.
int parsed = Integer.parseInt("42"); // 42.
~~~

Ngay cả khi giá trị không đổi, unary `+` vẫn áp dụng phép nâng kiểu số. Điều này quan trọng với `byte`, `short` và `char`.

## 4. Nâng kiểu số một ngôi

Với dấu `+` và `-` một ngôi, Java áp dụng **unary numeric promotion**:

| Toán hạng ban đầu | Kiểu của `+x` hoặc `-x` |
| --- | --- |
| `byte`, `short`, `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |
| `Byte`, `Short`, `Character` | Unbox rồi nâng lên `int` |
| `Integer`, `Long`, `Float`, `Double` | Unbox thành primitive tương ứng |

~~~java
byte b = 5;
int a = +b;  // 5, kieu int.
int c = -b;  // -5, kieu int.
// byte d = -b; // Loi: khong tu gan int vao byte.

char letter = 'A';
int codeUnit = +letter; // 65, kieu int.
~~~

`char` là đơn vị mã UTF-16, nên `+'A'` trả về `int` 65 chứ không phải một ký tự đã gắn dấu. Với wrapper số, quá trình **unboxing** có thể ném `NullPointerException`:

~~~java
Integer missing = null;
// int result = -missing; // Nem NullPointerException khi chay.
~~~

Hãy kiểm tra null nếu dữ liệu có thể thiếu.

## 5. Dấu trừ `-`: đổi dấu không phải lúc nào cũng an toàn

~~~java
int n = 12;
int opposite = -n; // -12; n van la 12.
~~~

Đổi dấu một số nguyên ở biên âm có thể **tràn** vì miền `int` bất đối xứng:

~~~java
int min = Integer.MIN_VALUE; // -2147483648.
int stillMin = -min;         // -2147483648 (tran int).
long correct = -(long) min; // 2147483648.
~~~

Giá trị toán học `2147483648` không biểu diễn được bằng `int`. Java không tự ném ngoại lệ ở phép đổi dấu nguyên thông thường. Nếu muốn **phát hiện tràn**, dùng `Math.negateExact(min)`, sẽ ném `ArithmeticException`. `Long.MIN_VALUE` có trường hợp tương tự.

Với số thực, dấu âm của **zero** được lưu lại:

~~~java
double negZero = -0.0;
System.out.println(negZero == 0.0); // true.
System.out.println(1.0 / negZero);  // -Infinity.
~~~

`+0.0` và `-0.0` bằng nhau theo primitive `==` nhưng khác bit dấu; dấu trừ một ngôi tạo `-0.0` từ `+0.0`, và dấu cộng một ngôi không xóa dấu âm của `-0.0`.

## 6. Phủ định `!` chỉ cho boolean

~~~java
boolean online = true;
boolean offline = !online; // false.

boolean ready = true;
boolean enabled = false;
boolean blocked = !(ready && enabled); // true.
~~~

| Biểu thức | Kết quả |
| --- | --- |
| `!true` | `false` |
| `!false` | `true` |
| `!!true` | `true` |
| `!(true && false)` | `true` |
| `!(true || false)` | `false` |

Đừng sử dụng `!` trên số nguyên như trong một số ngôn ngữ có truthiness:

~~~java
int count = 0;
// boolean wrong = !count; // Loi bien dich.
boolean empty = !(count > 0); // true.
~~~

`!` là **logical complement**; `~` mới là toán tử **bitwise complement** trên kiểu nguyên. Hai toán tử không thể thay thế cho nhau.

Với `Boolean`, Java tự **unbox** để áp dụng `!`, nên null có thể gây ngoại lệ:

~~~java
Boolean setting = null;
// boolean disabled = !setting; // Nem NullPointerException.
~~~

### Quy tắc De Morgan

Với biểu thức boolean `a` và `b`:

| Phủ định biểu thức ghép | Dạng biến đổi tương đương |
| --- | --- |
| `!(a && b)` | `!a || !b` |
| `!(a || b)` | `!a && !b` |

Trong trường hợp `a` và `b` có tác dụng phụ (gọi phương thức, thay đổi trạng thái), cần đánh giá ngữ nghĩa từng biểu thức khi refactor; với biến boolean thông thường, bảng giúp phủ định điều kiện đúng và dễ đọc.

## 7. Thứ tự ưu tiên và dấu ngoặc

Các toán tử một ngôi `+`, `-`, `!` có mức ưu tiên cao hơn các phép toán cộng/trừ hai ngôi và toán tử so sánh/logical:

~~~java
int a = 6;
int b = 2;
int first = -a + b;   // -4.
int second = -(a + b); // -8.

boolean smaller = !(a > b); // false.
~~~

Trong `-a + b`, phần `-a` là biểu thức con. Trong `-(a + b)`, dấu trừ áp dụng cho **toàn tổng**. Với `!` cũng phải phủ định **toàn điều kiện** khi cần:

~~~java
// boolean wrong = !a > b; // Sai kieu: !a yeu cau boolean.
boolean correct = !(a > b);
~~~

## 8. Bẫy thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`+x` luôn giữ nguyên kiểu `x`.” | `byte`, `short`, `char` được nâng thành `int` |
| “`-x` thay đổi trực tiếp `x`.” | Không, trả một giá trị mới |
| “`+ "12"` biến chuỗi thành số.” | Sai; dùng parsing như `Integer.parseInt` |
| “`!0` là true.” | Không hợp lệ: `!` cần boolean |
| “`!` giống `~`.” | `!` đảo logic; `~` đảo bit |
| “`-Integer.MIN_VALUE` là số dương.” | Tràn `int`, kết quả vẫn bằng `MIN_VALUE` |
| “`Boolean` có thể dùng `!` kể cả khi null.” | Null gây `NullPointerException` khi unbox |
| “`-0.0` giống `+0.0` trong mọi phép toán.” | Cùng `==` nhưng khác dấu ở nghịch đảo và bit biểu diễn |

## 9. Tự kiểm tra

1. `int x = 6; int y = -x;`, `x` và `y` bằng bao nhiêu?  
   *Đáp án:* 6 và -6.
2. `-(3 + 2)` khác `-3 + 2` thế nào?  
   *Đáp án:* -5 và -1.
3. `byte b = 7; var n = -b;`, kiểu `n` là gì?  
   *Đáp án:* `int`.
4. `var code = +'A';`, kiểu và giá trị `code` là gì?  
   *Đáp án:* `int`, 65.
5. `!(true && false)` có giá trị nào?  
   *Đáp án:* `true`.
6. `Boolean flag = null; boolean x = !flag;` có chạy bình thường không?  
   *Đáp án:* Không; ném `NullPointerException`.
7. `-Integer.MIN_VALUE` và `-(long) Integer.MIN_VALUE` khác nhau ra sao?  
   *Đáp án:* Kết quả `int` là -2147483648, còn `long` là 2147483648.
8. `1.0 / -0.0` trả gì?  
   *Đáp án:* `-Infinity`.

## Checklist

- [ ] Phân biệt `+x`/`-x` một ngôi với `a+b`/`a-b` hai ngôi.
- [ ] Hiểu `+` một ngôi không đổi giá trị nhưng có thể nâng kiểu số.
- [ ] Hiểu `-` đổi dấu và có thể tràn ở giá trị nguyên nhỏ nhất.
- [ ] Chỉ dùng `!` cho boolean, không cho số nguyên hoặc String.
- [ ] Kiểm tra null trước khi unbox wrapper.
- [ ] Nhớ số thực có `+0.0` và `-0.0` với bit dấu khác nhau.
- [ ] Dùng dấu ngoặc để phủ định đúng biểu thức mong muốn.
- [ ] Dùng `Math.negateExact` nếu nghiệp vụ yêu cầu phát hiện overflow khi đổi dấu.

**Kết luận:** Unary `+` và `-` áp dụng trên **toán hạng số sau khi nâng kiểu**, trong khi unary `!` chỉ áp dụng cho **boolean**. Nắm rõ kiểu kết quả, phạm vi ưu tiên và các tình huống biên như null, overflow và zero có dấu sẽ giúp sử dụng chính xác ba toán tử này.
