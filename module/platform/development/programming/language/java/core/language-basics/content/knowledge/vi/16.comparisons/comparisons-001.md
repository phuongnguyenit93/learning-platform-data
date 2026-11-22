# Toán tử `<`, `<=`, `>` và `>=` cho giá trị số — Java 17+

Java cung cấp bốn **toán tử so sánh quan hệ** (*relational operators*) để kiểm tra thứ tự của hai giá trị số. Mỗi phép so sánh có **hai toán hạng** và trả về **`boolean`**:

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `a < b` | `a` nhỏ hơn `b` | `3 < 5` | `true` |
| `a <= b` | `a` nhỏ hơn **hoặc bằng** `b` | `5 <= 5` | `true` |
| `a > b` | `a` lớn hơn `b` | `9 > 5` | `true` |
| `a >= b` | `a` lớn hơn **hoặc bằng** `b` | `5 >= 9` | `false` |

**Phân biệt quan trọng:** `<` và `>` là so sánh **nghiêm ngặt**, không bao gồm bằng nhau; `<=` và `>=` bao gồm trường hợp hai giá trị bằng nhau. Các dấu `<=`, `>=` được viết liền nhau; `=<` hoặc `=>` không phải toán tử Java.

~~~java
int age = 18;
boolean adult = age >= 18;   // true.
boolean minor = age < 18;    // false.
~~~

Toán tử không thay đổi giá trị của `age`. Nó chỉ sinh ra kết quả `boolean` có thể sử dụng trong `if`, `while`, `&&`, `||` hoặc biến boolean.

## 1. Điều kiện biên và tính đúng sai

Với hai giá trị số bình thường và không chứa NaN:

| Trường hợp | `a < b` | `a <= b` | `a > b` | `a >= b` |
| --- | --- | --- | --- | --- |
| `a = 3`, `b = 5` | true | true | false | false |
| `a = 5`, `b = 5` | false | true | false | true |
| `a = 9`, `b = 5` | false | false | true | true |

Một cách đọc dễ nhớ là điều kiện ở dấu `<=` hoặc `>=` đúng **khi một trong hai điều kiện “nhỏ/lớn hơn” hoặc “bằng” được thỏa mãn**.

Đừng lẫn với `==` và `!=`: đó là các phép kiểm tra **bằng/khác**, không phải toán tử xác định thứ tự. `a >= b` cũng không có nghĩa “`a` khác `b`”.

## 2. Demo Java 17+ chạy độc lập

Tạo file UTF-8 tên **`NumericRelationalDemo.java`**:

~~~java
public class NumericRelationalDemo {
    public static void main(String[] args) {
        int a = 7;
        int b = 10;

        System.out.println("less=" + (a < b));
        System.out.println("lessOrEqual=" + (a <= b));
        System.out.println("greater=" + (a > b));
        System.out.println("greaterOrEqual=" + (a >= b));

        System.out.println("equalLess=" + (a < a));
        System.out.println("equalLessOrEqual=" + (a <= a));
        System.out.println("equalGreater=" + (a > a));
        System.out.println("equalGreaterOrEqual=" + (a >= a));

        char firstLetter = 'A';
        char secondLetter = 'B';
        System.out.println("charComparison="
                + (firstLetter < secondLetter));

        int whole = 5;
        double fraction = 5.5;
        System.out.println("mixedIntDouble="
                + (whole < fraction));
        System.out.println("mixedLongDouble="
                + (10L > 9.5));

        Integer boxedInt = 7;
        Long boxedLong = 8L;
        System.out.println("wrapperComparison="
                + (boxedInt < boxedLong));

        int preciseInt = 16_777_217;
        float roundedFloat = 16_777_216f;
        System.out.println("intFloatGreater="
                + (preciseInt > roundedFloat));
        System.out.println("intFloatLessOrEqual="
                + (preciseInt <= roundedFloat));

        double nan = Double.NaN;
        System.out.println("nanLess=" + (nan < 5.0));
        System.out.println("nanLessOrEqual=" + (nan <= 5.0));
        System.out.println("nanGreater=" + (nan > 5.0));
        System.out.println("nanGreaterOrEqual=" + (nan >= 5.0));
        System.out.println("notNanGreater="
                + (!(nan > 5.0)));
        System.out.println("isNaN=" + Double.isNaN(nan));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zeroLess="
                + (negativeZero < positiveZero));
        System.out.println("zeroLessOrEqual="
                + (negativeZero <= positiveZero));
        System.out.println("zeroGreaterOrEqual="
                + (negativeZero >= positiveZero));

        System.out.println("positiveInfinityGreater="
                + (Double.POSITIVE_INFINITY > Double.MAX_VALUE));
        System.out.println("negativeInfinityLess="
                + (Double.NEGATIVE_INFINITY < -Double.MAX_VALUE));
        System.out.println("infinityGreaterOrEqualSelf="
                + (Double.POSITIVE_INFINITY
                        >= Double.POSITIVE_INFINITY));

        Integer missing = null;
        try {
            boolean unused = missing < 10;
            System.out.println("unexpected=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NullPointerException");
        }

        int overflowed = Integer.MAX_VALUE + 1;
        System.out.println("overflowedValue=" + overflowed);
        System.out.println("overflowedGreaterZero="
                + (overflowed > 0));
        long promotedBeforeAdd = (long) Integer.MAX_VALUE + 1;
        System.out.println("safeGreaterZero="
                + (promotedBeforeAdd > 0));

        boolean inRange = (a >= 0) && (a < b);
        System.out.println("inRange=" + inRange);
    }
}
~~~

Sử dụng **JDK 17 trở lên**, mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericRelationalDemo.java
java NumericRelationalDemo
~~~

**Exact expected stdout** của riêng lệnh `java NumericRelationalDemo`:

~~~text
less=true
lessOrEqual=true
greater=false
greaterOrEqual=false
equalLess=false
equalLessOrEqual=true
equalGreater=false
equalGreaterOrEqual=true
charComparison=true
mixedIntDouble=true
mixedLongDouble=true
wrapperComparison=true
intFloatGreater=false
intFloatLessOrEqual=true
nanLess=false
nanLessOrEqual=false
nanGreater=false
nanGreaterOrEqual=false
notNanGreater=true
isNaN=true
zeroLess=false
zeroLessOrEqual=true
zeroGreaterOrEqual=true
positiveInfinityGreater=true
negativeInfinityLess=true
infinityGreaterOrEqualSelf=true
nullUnboxing=NullPointerException
overflowedValue=-2147483648
overflowedGreaterZero=false
safeGreaterZero=true
inRange=true
~~~

Đầu ra của `java -version` và `javac -version` phụ thuộc JDK cài đặt, nên không nằm trong khối expected stdout cố định.

## 3. Kiểu toán hạng và phép nâng kiểu số hai ngôi

Bốn toán tử quan hệ trên dùng cho **kiểu số**: `byte`, `short`, `char`, `int`, `long`, `float`, `double` và các lớp bao số thích hợp được **unbox**. Khi hai toán hạng có kiểu khác nhau, Java áp dụng **binary numeric promotion** trước khi so sánh.

| Hai kiểu toán hạng | Kiểu được dùng khi so sánh | Ví dụ |
| --- | --- | --- |
| `byte` với `short` | `int` | `(byte) 1 < (short) 2` |
| `char` với `int` | `int` | `'A' < 66` |
| `int` với `long` | `long` | `5 < 6L` |
| `int` với `float` | `float` | `5 < 5.5f` |
| `long` với `double` | `double` | `10L > 9.5` |
| `float` với `double` | `double` | `1.5f < 2.0` |
| `Integer` với `Long` | Unbox rồi so theo `long` | `Integer.valueOf(7) < Long.valueOf(8)` |

**Kiểu của phép so sánh luôn là `boolean`**, không phải `int`/`double`. Trong `int n = 3; boolean result = n < 5;`, `n` vẫn là `int` và `result` là `boolean`.

### So sánh `char`

`char` là **đơn vị mã UTF-16 không dấu**, nên Java so sánh **giá trị số của đơn vị mã**, không dùng thứ tự từ điển theo ngôn ngữ:

~~~java
char a = 'A';
char b = 'B';
System.out.println(a < b); // true: 65 < 66.
~~~

Dùng `Collator` hoặc quy tắc so sánh chuỗi phù hợp nếu bài toán là sắp xếp tên/chuỗi theo ngôn ngữ tự nhiên. Không coi so sánh hai `char` là một bộ máy so sánh văn bản hoàn chỉnh.

### Wrapper và nguy cơ `null`

~~~java
Integer number = 7;
System.out.println(number < 10); // true do unboxing.

Integer missing = null;
// boolean check = missing < 10; // Khi chay nem NullPointerException.
~~~

Vì relational operator cần giá trị số nguyên thủy, wrapper thích hợp được unbox. Nếu wrapper là `null`, việc unbox ném `NullPointerException`. Trước khi so sánh dữ liệu có thể thiếu, hãy xác định quy tắc xử lý null, ví dụ:

~~~java
Integer input = null;
boolean valid = input != null && input >= 0;
// false, vế phải && không chạy nếu input null.
~~~

Với các kiểu tham chiếu như `String`, `Boolean` hoặc đối tượng không phải giá trị số có thể unbox, `<`/`<=`/`>`/`>=` không hợp lệ.

## 4. So sánh số nguyên và số thực: làm tròn khi nâng kiểu

Không phải mọi phép so sánh giữa `int`/`long` và `float`/`double` đều giữ nguyên khả năng phân biệt từng số nguyên.

`float` có khoảng **24 bit độ chính xác của phần trị**. Hai số nguyên lớn khác nhau có thể trở thành cùng một giá trị khi được chuyển thành `float`:

~~~java
int preciseInt = 16_777_217;
float roundedFloat = 16_777_216f;

System.out.println(preciseInt > roundedFloat);  // false.
System.out.println(preciseInt <= roundedFloat); // true.
~~~

Tại phép so sánh, `preciseInt` được đổi sang `float` và làm tròn thành **16_777_216f**, bằng `roundedFloat`. Đây không phải Java “so sánh sai”; kết quả tuân theo **quy tắc chuyển kiểu trước phép so sánh**.

`double` có khoảng **53 bit độ chính xác của phần trị**, vì vậy `long` rất lớn có thể gặp vấn đề tương tự khi so với `double`.

Nếu nghiệp vụ cần so sánh chính xác các số nguyên rất lớn, hãy chọn biểu diễn và kiểu toán hạng thích hợp (ví dụ cùng `long`, hoặc `BigInteger.compareTo` khi vượt miền `long`) thay vì âm thầm chuyển qua số thực xấp xỉ.

## 5. Trường hợp số thực đặc biệt: NaN, vô cực và zero có dấu

Các phép quan hệ `<`, `<=`, `>` và `>=` với `NaN` đều trả `false`; vì vậy phủ định một quan hệ không nhất thiết tương đương quan hệ đối nghịch:

~~~java
double x = Double.NaN;
System.out.println(x > 5.0);    // false
System.out.println(!(x > 5.0)); // true
System.out.println(x <= 5.0);   // false
~~~

Dùng `Double.isNaN(x)` để nhận diện NaN; khi dữ liệu chỉ được phép là số hữu hạn, dùng `Double.isFinite(x)` để loại cả NaN và vô cực.

`Double.POSITIVE_INFINITY` lớn hơn mọi số `double` hữu hạn; `Double.NEGATIVE_INFINITY` nhỏ hơn mọi số hữu hạn. Hai giá trị `+0.0` và `-0.0` không nhỏ hơn/lớn hơn nhau theo toán tử quan hệ primitive, nhưng `<=` và `>=` giữa chúng đều đúng. Các API như `Double.compare` và `Double.equals` có quy tắc riêng cho NaN và zero có dấu, được giải thích kỹ trong bài **NaN và những kết quả so sánh khác trực giác**.

## 6. Cú pháp, độ ưu tiên và điều kiện ghép

Bốn toán tử này có **độ ưu tiên thấp hơn phép cộng/nhân** nhưng **cao hơn `&&` và `||`**:

~~~java
int price = 8;
int tax = 2;
boolean affordable = price + tax <= 10; // true.

boolean range = (price >= 0) && (price < 10); // true.
~~~

Dấu ngoặc giúp biểu thị rõ ý nghĩa của điều kiện khoảng:

~~~java
int value = 7;
boolean inRange = value >= 0 && value < 10; // true.
~~~

Java **không hỗ trợ viết liên tiếp ba giá trị theo kiểu toán học `0 <= x < 10`**:

~~~java
int x = 7;
// boolean invalid = 0 <= x < 10; // Loi bien dich.
boolean valid = (0 <= x) && (x < 10);
~~~

Biểu thức `0 <= x` đã trả `boolean`, không thể làm toán hạng số của phép `< 10` tiếp theo. Cần tách thành hai phép so sánh rồi ghép bằng `&&`.

Lưu ý toán tử quan hệ trả `boolean` nên không dùng phép cộng hoặc trừ trực tiếp hai kết quả quan hệ như với số nguyên.

## 7. Tràn số trong **biểu thức trước** phép so sánh

Đúng toán tử quan hệ chưa đủ nếu toán hạng đã được tính sai vì overflow:

~~~java
int a = Integer.MAX_VALUE;
int overflowed = a + 1;

System.out.println(overflowed);     // -2147483648.
System.out.println(overflowed > 0); // false.
~~~

`a + 1` được đánh giá theo `int` trước khi phép so sánh diễn ra. Để cần kết quả lớn hơn `int`, **nâng kiểu trước phép tính**, không chỉ ép kiểu kết quả sau phép tính:

~~~java
int a = Integer.MAX_VALUE;

long correct = (long) a + 1;
System.out.println(correct > 0); // true.
~~~

Nếu bài toán yêu cầu **báo lỗi khi overflow** thay vì chuyển sang `long`, cân nhắc `Math.addExact`; với miền số nguyên vượt `long`, dùng `BigInteger.compareTo`. Với tính toán thập phân đòi hỏi chính xác, cân nhắc `BigDecimal.compareTo` và kiểm soát chính sách scale/rounding.

## 8. So sánh kiểu số và so sánh chuỗi là hai việc khác nhau

~~~java
int number = 12;
System.out.println(number > 9); // true.

// String text = "12";
// boolean invalid = text > "9"; // Loi bien dich.
~~~

`String` không phải kiểu số, ngay cả khi chứa chữ số. Muốn so **giá trị số**, phải parse/validate trước:

~~~java
int parsed = Integer.parseInt("12");
boolean numericGreater = parsed > 9; // true.
~~~

Muốn so **thứ tự từ điển của String**, dùng `String.compareTo(...)` hoặc bộ so sánh phù hợp thay vì toán tử `>`. Ví dụ `"12".compareTo("9") < 0` theo thứ tự từ điển ký tự, khác so sánh số 12 và 9.

## 9. Các lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`<`/`<=` trả số 0 hoặc 1.” | Chúng trả `boolean` |
| “`a <= b` chỉ đúng khi `a` nhỏ hơn `b`.” | Cũng đúng khi bằng nhau (trừ trường hợp bất thường như NaN) |
| “`0 <= x < 10` hợp lệ trong Java.” | Không; phải viết `0 <= x && x < 10` |
| “Hai wrapper số đem so bằng `<` sẽ so địa chỉ.” | Các wrapper số được unbox để so giá trị số |
| “Wrapper null so với số cho false.” | Có thể ném `NullPointerException` do unboxing |
| “`int` so với `float` luôn chính xác tuyệt đối.” | Numeric promotion có thể làm tròn số nguyên lớn |
| “`!(x > y)` luôn giống `x <= y`.” | Sai khi `x` hoặc `y` là NaN |
| “`+0.0` nhỏ hơn `-0.0` vì bit dấu khác.” | Chúng bằng nhau theo phép quan hệ primitive |
| “Thêm `> 0` tự sửa tràn số của toán hạng.” | Phải xử lý overflow **trước** khi so sánh |

## 10. Bài tập tự kiểm tra

1. `int a = 5, b = 5;` thì `a < b`, `a <= b`, `a > b` và `a >= b` là gì?  
   *Đáp án:* `false`, `true`, `false`, `true`.
2. `char a = 'A'; boolean c = a < 'B';` cho gì?  
   *Đáp án:* `true` vì so giá trị mã UTF-16 65 và 66.
3. `Integer a = 4; Long b = 5L; boolean c = a < b;` có hợp lệ không?  
   *Đáp án:* Có; unboxing và numeric promotion cho kết quả `true`.
4. `Integer x = null; boolean c = x < 10;` cho gì?  
   *Đáp án:* `NullPointerException` khi unbox.
5. `Double.NaN >= 0.0` và `!(Double.NaN < 0.0)` lần lượt là gì?  
   *Đáp án:* `false` và `true`.
6. Vì sao `int x = 16_777_217; float f = 16_777_216f; x > f` có thể là false?  
   *Đáp án:* `x` được chuyển sang `float` và làm tròn thành giá trị bằng `f`.
7. Viết điều kiện `10 <= score <= 20` trong Java.  
   *Đáp án:* `score >= 10 && score <= 20`.
8. `(Integer.MAX_VALUE + 1) > 0` là gì?  
   *Đáp án:* `false` do phép cộng `int` tràn trước khi so sánh.

## Checklist

- [ ] Phân biệt `<`, `<=`, `>`, `>=` và nhớ kết quả đều là `boolean`.
- [ ] Áp dụng so sánh quan hệ lên giá trị số, không lên `String`/`boolean`.
- [ ] Hiểu **unboxing** của wrapper và **binary numeric promotion**.
- [ ] Cẩn thận mất chính xác khi so số nguyên lớn với `float`/`double`.
- [ ] Với NaN, cả bốn phép quan hệ đều false; `!(a > b)` không luôn giống `a <= b`.
- [ ] Hiểu hai zero `+0.0` và `-0.0` so quan hệ bằng nhau.
- [ ] Viết điều kiện khoảng bằng hai phép so sánh nối bởi `&&`.
- [ ] Kiểm tra phép tính toán hạng có overflow trước khi tin vào kết quả so sánh.

**Kết luận:** `<`, `<=`, `>`, `>=` là các **toán tử quan hệ cho giá trị số** trong Java. Dùng chúng đúng không chỉ là nhớ dấu mà còn cần hiểu **kiểu số được so sánh**, **nâng kiểu**, **NaN** và **các phép tính xảy ra trước phép so sánh**.
