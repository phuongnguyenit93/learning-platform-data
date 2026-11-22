# `==` và `!=` trên kiểu nguyên thủy — Java 17+

## 1. Mục tiêu và quy tắc chính

Trong Java, hai toán tử so sánh bằng trên **kiểu nguyên thủy** (*primitive*) là:

- `a == b`: trả `true` nếu hai giá trị bằng nhau theo quy tắc của kiểu dữ liệu.
- `a != b`: trả `true` nếu hai giá trị không bằng nhau theo cùng quy tắc.

**Kết quả của cả hai toán tử luôn có kiểu `boolean`.** `!=` là phủ định kết quả của `==` khi đánh giá cùng hai toán hạng và cùng trạng thái.

~~~java
int x = 7;
int y = 7;
int z = 9;

System.out.println(x == y); // true
System.out.println(x != z); // true
System.out.println(x == z); // false
~~~

Với số nguyên, Java so sánh **giá trị số**, không so địa chỉ bộ nhớ. Với `boolean`, so sánh đúng/sai. Với `float` và `double`, so sánh theo quy tắc dấu phẩy động, có các trường hợp đặc biệt như `NaN`, `+0.0` và `-0.0`.

Bài này nói về **so sánh giá trị nguyên thủy**. Toán tử `==` giữa hai biến tham chiếu đối tượng có quy tắc khác; không được áp dụng suy luận của kiểu nguyên thủy một cách máy móc cho `String` hoặc wrapper.

## 2. Các kiểu nguyên thủy được so sánh như thế nào?

Java có tám kiểu nguyên thủy:

| Nhóm | Kiểu | `==`/`!=` hoạt động thế nào? |
|---|---|---|
| Số nguyên có dấu | `byte`, `short`, `int`, `long` | So sánh giá trị số sau chuyển đổi số học nếu cần |
| Mã UTF-16 không dấu | `char` | So sánh giá trị số của code unit, có thể so với kiểu số khác |
| Dấu phẩy động | `float`, `double` | So giá trị floating-point, có quy tắc `NaN` và zero có dấu |
| Logic | `boolean` | `true == true`, `false == false` là true; khác nhau là false |

Các kiểu số có thể tham gia so sánh số học với nhau, ví dụ `int == long` hoặc `char == int`. Nhưng **`boolean` không được trộn với kiểu số**:

~~~java
boolean ready = true;
System.out.println(ready == true);  // true
System.out.println(ready != false); // true

// boolean invalid = ready == 1; // LỖI COMPILE: boolean không so với int
~~~

Java không xem `true` như số nguyên 1 hoặc `false` như số 0.

## 3. So sánh `int`, `long`, `byte`, `short` và `char`

Với toán hạng số, Java áp dụng **binary numeric promotion** trước khi so sánh:

1. Nếu một toán hạng là `double`, chuyển toán hạng còn lại sang `double`.
2. Nếu không, nếu có `float`, chuyển sang `float`.
3. Nếu không, nếu có `long`, chuyển sang `long`.
4. Còn lại, so ở kiểu `int`; `byte`, `short`, `char` được nâng lên `int`.

Ví dụ:

~~~java
byte small = 10;
short medium = 10;
int count = 10;
long wide = 10L;

System.out.println(small == medium); // true
System.out.println(count == wide);   // true
System.out.println('A' == 65);       // true
System.out.println(10 != 11L);       // true
~~~

Ở `'A' == 65`, `char` mang giá trị UTF-16 bằng 65 và được chuyển sang `int` để so; điều này **không đồng nghĩa** Java đang so sánh chữ `"A"` kiểu `String` với một số.

Khi chỉ so các **kiểu số nguyên** ở miền giá trị biểu diễn được, widening từ `int` sang `long` không làm mất độ chính xác. Nhưng khi có `float` hoặc `double`, việc chuyển từ số nguyên rất lớn **có thể làm tròn**, cần chú ý phần sau.

### Giá trị và kiểu của biểu thức so sánh

~~~java
int left = 4;
long right = 4L;

var same = left == right; // same có kiểu boolean, giá trị true
System.out.println(same); // true
~~~

`var` suy ra `boolean` từ biểu thức `==`, không biến giá trị so sánh thành số hoặc chuỗi.

## 4. `==` không phải `=`

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `=` | Gán giá trị vào biến | `x = 7;` |
| `==` | Kiểm tra hai giá trị bằng nhau | `x == 7` |
| `!=` | Kiểm tra hai giá trị khác nhau | `x != 7` |

Ví dụ dễ mắc lỗi:

~~~java
boolean allowed = false;
if (allowed = true) { // Hợp lệ, nhưng GÁN true thay vì so sánh
    System.out.println("entered");
}
~~~

**Expected output:**

~~~text
entered
~~~

Trong Java, phép gán `allowed = true` là biểu thức có giá trị boolean `true`. Compiler chấp nhận, nhưng chương trình có thể sai nghiệp vụ.

Để kiểm tra boolean, ưu tiên:

~~~java
if (allowed) {
    // Chỉ chạy nếu allowed vốn đã true
}
if (!allowed) {
    // Chỉ chạy nếu allowed vốn là false
}
~~~

Với biến số `int`, `if (x = 1)` **không hợp lệ** do điều kiện `if` không thể là `int`; đừng áp dụng kết luận đó sang trường hợp gán `boolean`.

## 5. `float`/`double`: so chính xác giá trị đã biểu diễn, không có dung sai ngầm

Điểm dễ sai nhất khi dùng `==` với số thực:

~~~java
double calculated = 0.1 + 0.2;

System.out.println(calculated);        // 0.30000000000000004
System.out.println(calculated == 0.3); // false
System.out.println(calculated != 0.3); // true
~~~

`0.1`, `0.2` và `0.3` có thể không biểu diễn chính xác trong nhị phân hữu hạn. Biểu thức `0.1 + 0.2` được làm tròn và tạo giá trị `double` khác với giá trị biểu diễn của literal `0.3`.

**`==` không tự so “gần bằng”.** Hai số cùng hiển thị thành `0.30` khi định dạng hai chữ số sau dấu phẩy không nhất thiết có cùng giá trị nhị phân.

~~~java
double difference = (0.1 + 0.2) - 0.3;
System.out.println(difference); // 5.551115123125783E-17
~~~

Tuy nhiên, không nên kết luận rằng `==` trên `double` **luôn sai**: nếu bài toán cố ý kiểm tra sự bằng nhau của **giá trị floating-point đã được biểu diễn**, `==` là toán tử hợp lệ. Vấn đề là không được dùng nó để thay một khái niệm **bằng nhau trong phạm vi sai số** mà chưa định nghĩa rõ.

## 6. `float` so với `double` có thể khác dù cùng literal thập phân

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println((double) f); // 0.10000000149011612
System.out.println(f == d);     // false
~~~

`0.1f` được làm tròn về định dạng **binary32**, còn `0.1` là literal **binary64**. Khi so sánh, `float f` được nâng sang `double`, nhưng **giá trị đã bị làm tròn ở float không được phục hồi**.

Quy tắc tổng quát: cùng cách viết thập phân **không bảo đảm** hai biến `float` và `double` mang cùng giá trị sau chuyển kiểu.

## 7. So sánh số nguyên lớn với số thực: bẫy làm tròn

Khi một toán hạng số nguyên được chuyển sang `float` hoặc `double`, những số nguyên đủ lớn có thể **mất khả năng phân biệt từng đơn vị**.

~~~java
int exactInt = 16_777_217;          // 2^24 + 1
float roundedFloat = 16_777_216f;   // 2^24

System.out.println(exactInt == roundedFloat); // true
~~~

Kết quả tưởng vô lý nhưng hợp lệ: Java chuyển `int` sang `float` theo numeric promotion. Tại độ lớn `2^24`, binary32 không biểu diễn mọi số nguyên liên tiếp; `16_777_217` được làm tròn về `16_777_216f`, nên hai toán hạng cuối cùng bằng nhau.

Tương tự:

~~~java
long exactLong = 9_007_199_254_740_993L;   // 2^53 + 1
double roundedDouble = 9_007_199_254_740_992d; // 2^53

System.out.println(exactLong == roundedDouble); // true
~~~

Đây **không** phải `long` có cùng giá trị toán học với `double` ban đầu; kiểu `long` bị chuyển thành `double` cho phép so sánh và mất một đơn vị.

**Khuyến nghị:** khi nghiệp vụ cần so ID, số đếm hay tiền dưới dạng số nguyên lớn, **giữ cùng họ kiểu số nguyên** (`long`, `BigInteger` nếu cần) thay vì trộn với floating-point.

## 8. `NaN`: ngoại lệ của phép bằng và khác

~~~java
double nan = Double.NaN;
System.out.println(nan == nan); // false
System.out.println(nan != nan); // true
~~~

Với kiểu nguyên thủy `float`/`double`, NaN không bằng bất cứ giá trị nào kể cả chính nó; `!=` trả `true` nếu có NaN. Dùng `Double.isNaN` hoặc `Float.isNaN` để nhận diện, thay vì so với hằng NaN. `Double.equals` và `Double.compare` dùng các quy tắc khác cho wrapper và thứ tự sắp xếp; bài riêng về **NaN** trình bày ví dụ chi tiết.

## 9. `+0.0` và `-0.0` bằng nhau dưới `==`

~~~java
System.out.println(0.0 == -0.0); // true
System.out.println(0.0 != -0.0); // false
System.out.println(1.0 / -0.0);  // -Infinity
~~~

Zero có dấu khác nhau về bit biểu diễn và có thể ảnh hưởng các phép tính như nghịch đảo, nhưng primitive `==` không phân biệt. Khi yêu cầu phải phân biệt dấu zero hoặc bit, chọn API như `Double.compare` hay `Double.doubleToRawLongBits` theo hợp đồng.

## 10. Infinity và dữ liệu hữu hạn

~~~java
System.out.println(Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY); // true
System.out.println(Double.POSITIVE_INFINITY != Double.NEGATIVE_INFINITY); // true
~~~

Infinity cùng dấu bằng nhau và Infinity trái dấu khác nhau khi dùng primitive `==`/`!=`. Nhưng bằng chính nó không chứng minh số đó hữu hạn: hãy dùng `Double.isFinite` khi đầu vào phải là số thực hữu hạn.

## 11. Khi nào cần so gần bằng nhau?

Giá trị `0.1 + 0.2` khác `0.3` ở biểu diễn binary64, nên `==` trả `false`. Nếu bài toán muốn so kết quả đo hoặc tính toán trong **một mức sai số được phép**, cần định nghĩa dung sai theo đơn vị và quy mô thay vì thay bằng một epsilon tùy ý.

Trong demo cuối bài, `nearlyEqual(a, b, tolerance)` là ví dụ so bằng dung sai tuyệt đối khi **cả hai đầu vào và dung sai hữu hạn**. Bài **So sánh số thực bằng sai số phù hợp yêu cầu** phân tích đầy đủ sai số tuyệt đối, tương đối, kết hợp, miền gần 0 và các giới hạn tràn số.

## 12. Phân biệt primitive với reference `==`

Ở primitive:

~~~java
int a = 1000;
int b = 1000;
System.out.println(a == b); // true
~~~

Với hai object `String` được tạo riêng:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: hai tham chiếu khác nhau
System.out.println(first.equals(second)); // true: nội dung bằng nhau
~~~

**Không coi `==` là toán tử so nội dung của mọi object.** Nó so giá trị đối với primitive, nhưng giữa hai reference phù hợp thì so cùng/khác object. `!=` có phân biệt tương ứng.

Một chi tiết quan trọng khi có wrapper:

~~~java
int primitive = 10;
Integer boxed = 10;

System.out.println(primitive == boxed); // true: Integer được unbox để so số
~~~

Nhưng `Integer` có thể là `null`:

~~~java
Integer nullable = null;
// System.out.println(primitive == nullable);
// Có thể ném NullPointerException khi unbox null.
~~~

So **hai reference wrapper** mà không unbox không đồng nghĩa so hai primitive. Khi mục đích là so **giá trị object**, chọn API so sánh phù hợp như `equals` hoặc `Objects.equals`, dựa trên chính sách xử lý null của ứng dụng.

## 13. Lỗi biên dịch và bẫy logic phổ biến

| Viết hoặc suy luận sai | Vấn đề | Cách đúng |
|---|---|---|
| `if (x = 1)` với x là int | Biểu thức gán cho int, không phải boolean | `if (x == 1)` |
| `if (flag = true)` để so boolean | Vô tình gán true; đoạn code vẫn compile | `if (flag)` |
| `true == 1` | Boolean không chuyển sang số | Chỉ so boolean với boolean |
| `'A' == 65` chắc chắn false vì khác kiểu | Numeric promotion so giá trị số | Kết quả `true` |
| `0.1 + 0.2 == 0.3` phải true | Sai số biểu diễn binary64 | Dung sai có chủ đích hoặc decimal exact |
| `0.1f == 0.1` phải true | float/double lưu xấp xỉ khác nhau | Hiểu conversion trước khi so |
| `nan == nan` phải true | NaN không bằng bất kỳ số nào, kể cả nó | `Double.isNaN(nan)` |
| `0.0 != -0.0` phải true | Signed zero so bằng nhau | So bit nếu cần phân biệt |
| `intLarge == floatValue` luôn chính xác | int chuyển sang float có thể làm tròn | Giữ kiểu nguyên khi so giá trị nguyên lớn |
| `Integer a == Integer b` luôn so số | Nếu đều reference, có thể so cùng object | Dùng `equals` hoặc unbox có kiểm tra |
| `wrapper == primitive` không bao giờ lỗi | Wrapper null có thể NPE khi unbox | Kiểm tra null |
| `a != b` là so gần khác nhau | `!=` phủ định phép so bằng chính xác | Định nghĩa tolerance cho dữ liệu đo |

## 14. Ví dụ Java 17 độc lập, chạy được

Lưu file đúng tên **`PrimitiveEqualityDemo.java`**:

~~~java
public final class PrimitiveEqualityDemo {
    private PrimitiveEqualityDemo() {}

    static boolean nearlyEqual(double a, double b, double tolerance) {
        if (!Double.isFinite(tolerance) || tolerance < 0) {
            throw new IllegalArgumentException("invalid tolerance");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b) <= tolerance;
    }

    public static void main(String[] args) {
        int a = 7;
        int b = 7;
        int c = 9;
        System.out.println("int equal=" + (a == b));
        System.out.println("int not equal=" + (a != c));

        byte small = 10;
        short medium = 10;
        System.out.println("byte short=" + (small == medium));

        int number = 10;
        long wide = 10L;
        System.out.println("int long=" + (number == wide));
        System.out.println("char numeric=" + ('A' == 65));

        boolean ready = true;
        boolean enabled = false;
        System.out.println("boolean equal=" + (ready == enabled));
        System.out.println("boolean not equal=" + (ready != enabled));

        double calculated = 0.1 + 0.2;
        System.out.println("decimal sum=" + calculated);
        System.out.println("decimal equal=" + (calculated == 0.3));
        System.out.println("decimal not equal=" + (calculated != 0.3));
        System.out.println("decimal near="
                + nearlyEqual(calculated, 0.3, 1e-12));

        float f = 0.1f;
        double d = 0.1;
        System.out.println("float double equal=" + (f == d));

        int exactInt = 16_777_217;
        float roundedFloat = 16_777_216f;
        System.out.println("int float equal=" + (exactInt == roundedFloat));

        long exactLong = 9_007_199_254_740_993L;
        double roundedDouble = 9_007_199_254_740_992d;
        System.out.println("long double equal=" + (exactLong == roundedDouble));

        double nan = Double.NaN;
        System.out.println("NaN equal=" + (nan == nan));
        System.out.println("NaN not equal=" + (nan != nan));
        System.out.println("isNaN=" + Double.isNaN(nan));

        System.out.println("signed zero equal=" + (0.0 == -0.0));
        System.out.println("signed zero not equal=" + (0.0 != -0.0));
        System.out.println("positive zero reciprocal=" + (1.0 / 0.0));
        System.out.println("negative zero reciprocal=" + (1.0 / -0.0));

        System.out.println("same infinity="
                + (Double.POSITIVE_INFINITY == (1.0 / 0.0)));
        System.out.println("opposite infinity="
                + (Double.POSITIVE_INFINITY != Double.NEGATIVE_INFINITY));

        Integer boxed = 10;
        System.out.println("boxed primitive=" + (boxed == number));
        Integer missing = null;
        try {
            System.out.println(number == missing);
        } catch (NullPointerException ex) {
            System.out.println("boxed null=NullPointerException");
        }

        String first = new String("Java");
        String second = new String("Java");
        System.out.println("reference equal=" + (first == second));
        System.out.println("content equal=" + first.equals(second));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục chứa `PrimitiveEqualityDemo.java`; không cần Maven/Gradle hoặc thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveEqualityDemo.java
java -cp . PrimitiveEqualityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveEqualityDemo.java
java -cp . PrimitiveEqualityDemo
~~~

**Exact expected stdout:**

~~~text
int equal=true
int not equal=true
byte short=true
int long=true
char numeric=true
boolean equal=false
boolean not equal=true
decimal sum=0.30000000000000004
decimal equal=false
decimal not equal=true
decimal near=true
float double equal=false
int float equal=true
long double equal=true
NaN equal=false
NaN not equal=true
isNaN=true
signed zero equal=true
signed zero not equal=false
positive zero reciprocal=Infinity
negative zero reciprocal=-Infinity
same infinity=true
opposite infinity=true
boxed primitive=true
boxed null=NullPointerException
reference equal=false
content equal=true
~~~

### Những dòng dễ bất ngờ

- `int long=true`: giá trị nguyên 10 vẫn giữ chính xác khi chuyển rộng từ int sang long.
- `char numeric=true`: `'A'` có giá trị số 65.
- `decimal equal=false`: `0.1 + 0.2` và `0.3` không phải cùng giá trị binary64.
- `float double equal=false`: `0.1f` và `0.1` được làm tròn ở độ chính xác khác nhau.
- `int float equal=true` / `long double equal=true`: **chuyển kiểu để so có thể mất độ chính xác**, không phải các số nguyên ban đầu bằng nhau về toán học.
- `NaN equal=false`, `NaN not equal=true`: quy tắc NaN đặc biệt.
- `signed zero equal=true`: `+0.0` và `-0.0` bằng nhau dưới toán tử `==`, dù nghịch đảo cho Infinity khác dấu.
- `boxed primitive=true`: unboxing cho phép so giá trị số, còn wrapper null gây NPE.
- `reference equal=false`: `==` giữa hai String reference không so nội dung; `equals` mới cho true.

## 15. Bài tập có đáp án

### Bài A — nguyên thủy với kiểu khác nhau

~~~java
byte a = 65;
char b = 'A';
System.out.println(a == b);
~~~

**Đáp án:** `true`, vì numeric promotion đưa hai toán hạng về int có cùng giá trị 65.

### Bài B — boolean và số

~~~java
boolean active = true;
// System.out.println(active == 1);
~~~

**Đáp án:** dòng comment nếu bỏ comment sẽ **lỗi compile**. Java không so boolean với int.

### Bài C — NaN

~~~java
double x = Double.NaN;
System.out.println(x == x);
System.out.println(x != x);
~~~

**Đáp án:**

~~~text
false
true
~~~

Dùng `Double.isNaN(x)` khi muốn nhận diện NaN.

### Bài D — sai số số thực

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3);
~~~

**Đáp án:** `false`. Nếu mục đích là gần bằng theo sai số cho phép, cần quy tắc dung sai; nếu nghiệp vụ yêu cầu thập phân chính xác, cân nhắc `BigDecimal` từ chuỗi.

### Bài E — số nguyên lớn và float

~~~java
int n = 16_777_217;
float f = 16_777_216f;
System.out.println(n == f);
~~~

**Đáp án:** `true` vì `n` bị làm tròn khi chuyển sang float trước khi so.

### Bài F — khác `=` và `==`

~~~java
boolean ok = false;
if (ok = true) {
    System.out.println("entered");
}
~~~

**Đáp án:** in `entered`. Đây là **gán** `true` cho `ok`, không phải kiểm tra giá trị cũ.

### Bài G — reference hay primitive?

~~~java
int a = 5, b = 5;
String x = new String("5");
String y = new String("5");
System.out.println(a == b);
System.out.println(x == y);
System.out.println(x.equals(y));
~~~

**Đáp án:**

~~~text
true
false
true
~~~

`int` được so theo giá trị; `String` cần `equals` để so nội dung.

## 16. Checklist và kết luận

- [ ] Biết `==` so bằng, `!=` so khác và trả kết quả `boolean`.
- [ ] Phân biệt `=` gán và `==` so sánh.
- [ ] Hiểu `boolean` chỉ so được với biểu thức boolean phù hợp.
- [ ] Biết `byte`, `short`, `char` có thể được nâng lên `int` khi so.
- [ ] Biết `int` và `long` có thể so chính xác khi chuyển rộng int → long.
- [ ] Nhận ra numeric promotion sang `float`/`double` có thể mất độ chính xác số nguyên lớn.
- [ ] Không xem `==` trên số thực là so “gần bằng”.
- [ ] Biết `NaN == NaN` là false, `NaN != NaN` là true.
- [ ] Biết `+0.0 == -0.0` là true, dù bit và một số phép tính khác phân biệt.
- [ ] Biết Infinity cùng dấu có thể so bằng; dữ liệu hữu hạn cần kiểm tra riêng.
- [ ] Có thể định nghĩa dung sai dựa trên miền/đơn vị nếu bài toán cần gần bằng.
- [ ] Phân biệt primitive comparison với reference identity; wrapper có thể unbox và gặp null.
- [ ] Biên dịch/chạy `PrimitiveEqualityDemo.java` bằng `javac`/`java`, đối chiếu stdout chính xác.

**Kết luận:** Với primitive Java 17+, `==`/`!=` kiểm tra **giá trị**, không so tham chiếu. Các kiểu số áp dụng numeric promotion trước khi so; riêng floating-point cần đặc biệt chú ý sai số biểu diễn, NaN, zero có dấu và việc chuyển từ số nguyên lớn sang float/double. Hãy dùng toán tử chính xác khi muốn **giá trị đúng bằng nhau**, và định nghĩa quy tắc dung sai khi muốn **gần bằng nhau** theo yêu cầu bài toán.