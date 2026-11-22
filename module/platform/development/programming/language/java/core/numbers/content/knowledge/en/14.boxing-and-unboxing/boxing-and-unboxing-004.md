# So sánh `==` giữa hai wrapper và giữa wrapper với primitive trong Java

Java có hai nhóm kiểu thường gặp khi biểu diễn số: **primitive** (`int`, `long`, `double`, …) và **wrapper** (`Integer`, `Long`, `Double`, …). Wrapper là **đối tượng tham chiếu** chứa một giá trị primitive tương ứng. Điều này làm cho cùng ký hiệu `==` có thể mang hai ý nghĩa rất khác nhau:

- Khi **cả hai toán hạng là các wrapper có cùng kiểu tham chiếu**, `==` thường so sánh **có cùng đối tượng hay không** (*reference identity*), chứ không so sánh giá trị số.
- Khi **một toán hạng là wrapper số còn toán hạng kia là primitive số**, Java thường **unbox** wrapper, áp dụng chuyển kiểu số học thích hợp rồi so sánh **giá trị số**.
- Nếu wrapper cần unbox là `null`, thao tác có thể ném **`NullPointerException`**.
- `equals` và `Objects.equals` dùng quy tắc bằng nhau của đối tượng, khác `==` tham chiếu. Với các wrapper số, `equals` thường đòi hỏi **cùng loại wrapper và cùng giá trị theo quy tắc của loại đó**.

Hiểu rõ **kiểu tĩnh của hai toán hạng** và **có xảy ra unboxing không** là chìa khóa để giải thích một phép so sánh.

## 1. Phân biệt primitive, wrapper và boxing/unboxing

| Primitive | Wrapper tương ứng | Ví dụ |
| --- | --- | --- |
| `byte` | `Byte` | `byte n = 7; Byte w = n;` |
| `short` | `Short` | `Short w = (short) 7;` |
| `char` | `Character` | `Character w = 'A';` |
| `int` | `Integer` | `Integer w = 7;` |
| `long` | `Long` | `Long w = 7L;` |
| `float` | `Float` | `Float w = 7.0f;` |
| `double` | `Double` | `Double w = 7.0;` |
| `boolean` | `Boolean` | `Boolean w = true;` |

**Autoboxing** chuyển primitive thành wrapper khi ngữ cảnh cho phép:

```java
int value = 42;
Integer boxed = value; // int -> Integer
```

**Unboxing** chuyển wrapper về primitive:

```java
Integer boxed = 42;
int plain = boxed; // Integer -> int
```

Wrapper có thể là `null`; primitive số không thể là `null`. Các ví dụ ngắn trong phần giải thích được viết để đặt bên trong method/class, trừ khi có ghi rõ là chương trình chạy độc lập.

## 2. Hai wrapper `Integer`: `==` so sánh tham chiếu

`Integer` là một class. Với hai biến `Integer`, Java có thể dùng toán tử `==` cho **reference equality**:

```java
Integer a = Integer.valueOf(42);
Integer b = a;
boolean sameObject = (a == b); // true vì b trỏ đúng object của a
```

Nếu hai wrapper là hai object khác nhau nhưng chứa cùng giá trị `int`, `==` của hai tham chiếu sẽ là `false`; `equals` có thể vẫn `true`. Tuy nhiên, với `Integer.valueOf` và autoboxing, JVM có thể **tái sử dụng object**, khiến hai phép boxing riêng cùng trỏ một object.

**Không được kết luận** rằng `Integer x = 1000; Integer y = 1000; x == y` luôn có kết quả `false`. Với một số giá trị, implementation có thể cache thêm ngoài mức tối thiểu; code đúng phải **không phụ thuộc** identity của các wrapper được boxing riêng.

### Vì sao cache từ -128 đến 127 dễ đánh lừa người học?

Java bảo đảm việc boxing các giá trị `int` thuộc khoảng **-128 đến 127** dùng đối tượng được tái sử dụng theo quy định của ngôn ngữ. Do đó:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b);      // true: khoảng cache bảo đảm
System.out.println(a.equals(b)); // true: cùng giá trị int
```

Nhưng bên ngoài khoảng bảo đảm:

```java
Integer x = 1_000;
Integer y = 1_000;

// Không viết chương trình nghiệp vụ phụ thuộc vào (x == y).
// Dùng:
boolean equalValues = x.equals(y); // true
```

Tại sao nhiều tài liệu nói `128 == 128` với hai `Integer` cho `false`? Đó là kết quả thường thấy của cấu hình JVM phổ biến, **không phải hợp đồng chung mà chương trình được quyền dựa vào**. Một số wrapper nguyên khác cũng có quy tắc tái sử dụng giá trị boxing nhỏ; vì thế cache không nên trở thành cách kiểm tra giá trị số.

### Tham chiếu giống hệt nhau vẫn luôn `==`

```java
Integer n = Integer.valueOf(500);
Integer alias = n;
System.out.println(n == alias); // true, bất kể n có trong cache hay không
```

Đây là identity của object, không liên quan tới miền giá trị của `int`.

## 3. Wrapper và primitive: unboxing để so sánh giá trị

Khi một vế là primitive số và vế kia là wrapper số, Java thực hiện **unboxing conversion** ở toán hạng wrapper, sau đó so sánh số học theo quy tắc chuyển kiểu thích hợp:

```java
Integer boxed = 1_000;
int primitive = 1_000;
System.out.println(boxed == primitive); // true
System.out.println(primitive == boxed); // true
```

Điều này **khác hẳn** `Integer == Integer`. So sánh ở đây không hỏi hai tham chiếu có chung object nào; `primitive` không phải tham chiếu.

Một ví dụ khác với widening:

```java
Integer a = 10;
long b = 10L;
System.out.println(a == b); // true: Integer -> int, int -> long
```

Hoặc:

```java
Long wrapped = 10L;
int primitive = 10;
System.out.println(wrapped == primitive); // true: Long -> long; int -> long
```

**Giá trị có thể được chuyển kiểu trước khi so sánh.** Nếu có số thực, numeric promotion có thể gây mất precision ở giá trị lớn, ví dụ `long` được mở rộng sang `double`. Đừng hiểu một phép `==` có unboxing là phép so sánh “chính xác tuyệt đối cho mọi cặp số” sau mọi chuyển kiểu.

### Tình huống ngược: ép wrapper thành primitive tường minh

Khi mục đích là so sánh giá trị giữa hai wrapper, bạn có thể làm rõ bằng unbox:

```java
Integer left = 1_000;
Integer right = 1_000;
boolean equalInts = (left.intValue() == right.intValue()); // true
```

Cách này dễ hiểu, nhưng cả hai lời gọi `intValue()` sẽ ném `NullPointerException` nếu tham chiếu tương ứng là `null`. Nếu không cần unbox, `left.equals(right)` hoặc `Objects.equals(left, right)` thường gọn hơn.

## 4. Khi có `null`, `==` có thể an toàn hoặc ném exception

`Integer` là tham chiếu nên có thể chứa `null`:

```java
Integer missing = null;
Integer alsoMissing = null;
System.out.println(missing == alsoMissing); // true: cả hai tham chiếu null
System.out.println(missing == null);        // true: không unbox
```

Ngược lại:

```java
Integer missing = null;
int zero = 0;
// System.out.println(missing == zero); // NPE lúc chạy vì phải unbox missing
```

Dòng được chú thích **biên dịch hợp lệ** nhưng ném `NullPointerException` nếu thực thi. So sánh `missing == null` không gây unboxing vì vế còn lại là literal `null` tham chiếu, không phải giá trị `int` 0.

### Cách kiểm tra null trước khi unbox

```java
Integer count = null;
boolean isTen = count != null && count == 10; // false, an toàn
```

`&&` đánh giá từ trái sang phải và **short-circuit**: nếu `count != null` là `false`, vế `count == 10` không được thực thi.

Đổi thứ tự sẽ mất an toàn:

```java
Integer count = null;
// boolean wrong = count == 10 && count != null;
// nếu thực thi, NPE ngay tại count == 10
```

Đối với object:

```java
Integer a = null;
Integer b = null;
boolean bothMissing = java.util.Objects.equals(a, b); // true
```

Cần xem **hai giá trị cùng thiếu** có thực sự được nghiệp vụ coi là bằng nhau không. `Objects.equals(null, null)` trả `true` theo contract, nhưng một rule xác thực đầu vào có thể đòi hỏi cả hai đều khác `null`.

## 5. `equals` và `Objects.equals` so sánh điều gì?

Với hai `Integer`, `a.equals(b)` so sánh **giá trị nguyên** khi `b` cũng là một `Integer`:

```java
Integer a = 1_000;
Integer b = 1_000;
System.out.println(a.equals(b)); // true
```

`equals` là method trên tham chiếu bên trái. Nếu `a == null`, lời gọi `a.equals(b)` gây NPE. `Objects.equals(a, b)` là tiện ích so sánh có xử lý null:

```java
Integer a = null;
Integer b = 7;
System.out.println(java.util.Objects.equals(a, b)); // false
System.out.println(java.util.Objects.equals(null, null)); // true
```

Bảng quyết định:

| Cú pháp | Khi hai đối số là `Integer` | Khi có `null` |
| --- | --- | --- |
| `a == b` | So sánh cùng tham chiếu object | Hai null bằng nhau, một null thì khác |
| `a.equals(b)` | So sánh cùng loại wrapper và giá trị | NPE nếu chính `a` là null |
| `Objects.equals(a, b)` | So sánh bằng `equals` khi khác null | Không NPE; hai null được coi bằng nhau |
| `a.intValue() == b.intValue()` | So sánh hai giá trị primitive `int` | NPE nếu một wrapper là null |

**Không thay toàn bộ `==` trong chương trình bằng `equals`**: primitive không gọi được method, và nhiều nơi bạn chủ đích muốn so sánh tham chiếu. Hãy xác định ý nghĩa mong muốn trước.

## 6. Hai wrapper kiểu số khác nhau: một trường hợp dễ nhầm

`Integer` và `Long` là **hai class không có quan hệ kế thừa trực tiếp** và không tự động trở thành cùng kiểu chỉ vì chúng đều chứa số nguyên.

```java
Integer i = 7;
Long l = 7L;

System.out.println(i.equals(l)); // false: Integer và Long khác loại
System.out.println(i.longValue() == l.longValue()); // true
```

Nếu viết `i == l` với hai toán hạng đều là tham chiếu `Integer` và `Long`, Java **báo lỗi biên dịch** vì hai kiểu tham chiếu không thể so sánh bằng `==` theo quy tắc reference equality trong trường hợp này. Nó **không tự động unbox cả hai wrapper số khác kiểu** để chọn phép so sánh số học.

Muốn so sánh theo giá trị, chuyển các toán hạng thành primitive rõ ràng, hoặc chọn API so sánh theo miền số đã xác định:

```java
Integer i = 7;
Long l = 7L;

boolean equal = i.longValue() == l.longValue(); // true
// boolean invalid = i == l; // lỗi biên dịch
```

Khi dùng `equals`, `Integer.valueOf(7).equals(Long.valueOf(7L))` là `false` dù giá trị toán học đều là 7. `Objects.equals` không tự chuyển loại wrapper: nó vẫn theo định nghĩa `equals` của object.

### Cẩn thận với so sánh `long` và `double`

```java
long exactLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedDouble = 9_007_199_254_740_992.0;
System.out.println(exactLong == roundedDouble); // true
```

Khi `long` so sánh với `double`, Java nâng `long` sang `double`; số nguyên quá lớn có thể bị làm tròn. `==` vì vậy có thể trả `true` cho hai dữ liệu có nguồn toán học ban đầu khác nhau. Đây là giới hạn của việc chuyển kiểu số học, không liên quan cache wrapper.

Nếu nghiệp vụ cần so sánh ID nguyên chính xác, không chuyển chúng qua `double`.

## 7. `Double`, `Float`: bằng nhau số học và bằng nhau object không đồng nhất

Hai giá trị primitive `double` được so sánh số học theo IEEE 754:

```java
double posZero = +0.0;
double negZero = -0.0;
System.out.println(posZero == negZero); // true
```

Nhưng `Double.equals` phân biệt bit dấu của zero:

```java
Double pos = Double.valueOf(+0.0);
Double neg = Double.valueOf(-0.0);
System.out.println(pos.equals(neg)); // false
System.out.println(pos == +0.0);     // true: unbox pos và so sánh primitive
System.out.println(neg == +0.0);     // true: unbox neg, primitive -0.0 == +0.0
```

Lưu ý ở đây `pos.equals(neg)` khác `pos == +0.0` vì **khác cơ chế so sánh**; câu đầu dùng định nghĩa `equals` của wrapper, câu sau unbox để dùng so sánh primitive.

Tương tự, `NaN`:

```java
double nan = Double.NaN;
System.out.println(nan == nan); // false theo IEEE 754

Double boxedNaN1 = Double.valueOf(Double.NaN);
Double boxedNaN2 = Double.valueOf(Double.NaN);
System.out.println(boxedNaN1.equals(boxedNaN2)); // true
```

**Không sử dụng `==` giữa hai tham chiếu `Double` để kiểm tra hai giá trị NaN**: đó là so sánh object identity và phụ thuộc việc tạo/tái sử dụng object, không trực tiếp nói lên ngữ nghĩa NaN.

`Float` có điểm tương ứng với zero có dấu và NaN. Các ngoại lệ này là lý do nên chọn phép so sánh theo yêu cầu cụ thể chứ không áp dụng khẩu quyết “wrapper thì chỉ dùng equals” một cách máy móc.

## 8. Wrapper trong collection: `HashSet`, `HashMap` và lookup

Collections dạng `HashSet<Integer>` và khóa của `HashMap<Integer, …>` hoạt động qua `equals` và `hashCode`, **không** dùng `==` tham chiếu để quyết định phần tử trùng nhau.

```java
java.util.Set<Integer> values = new java.util.HashSet<>();
values.add(1_000);
values.add(1_000);
System.out.println(values.size()); // 1
```

Ở dòng đầu của đoạn trên, việc Java có cache wrapper 1000 hay không hoàn toàn không ảnh hưởng kết quả set. Hai lần thêm cùng giá trị `Integer` được xem là trùng theo `equals`.

Ngược lại, tập `HashSet<Double>` **phân biệt `+0.0` và `-0.0`**, vì `Double.equals` phân biệt chúng:

```java
java.util.Set<Double> zeros = new java.util.HashSet<>();
zeros.add(+0.0);
zeros.add(-0.0);
System.out.println(zeros.size()); // 2
```

Điều này nhắc rằng một phép so sánh dùng cho khóa phải đúng **hợp đồng ngữ nghĩa**. Nếu ứng dụng muốn zero có dấu là một khóa, hãy chủ động chuẩn hóa giá trị theo chính sách, thay vì giả định mọi API coi chúng bằng nhau.

## 9. Điều gì diễn ra trong overload, biểu thức và toán tử điều kiện?

Khi đưa wrapper vào phương thức nhận primitive, Java có thể unbox theo quy tắc gọi method:

```java
static boolean positive(int value) {
    return value > 0;
}

Integer boxed = 10;
// positive(boxed) -> true: Java unbox Integer thành int
```

Đây là một method và lời gọi minh họa đặt trong class/method phù hợp. Nếu `boxed` là `null`, unboxing sẽ ném NPE.

### `==` không phải lúc nào cũng unbox

```java
Integer a = 10;
Integer b = 10;
int c = 10;

boolean wrapperWrapper = a == b; // reference equality
boolean wrapperPrimitive = a == c; // numeric equality sau unboxing
```

Đừng nhìn vào giá trị đều là 10 mà bỏ qua kiểu tĩnh. Kết quả của biểu thức thay đổi vì overload ngữ nghĩa của toán tử `==` được chọn khác nhau.

### Toán tử `+` kích hoạt unboxing trước so sánh

```java
Integer a = 10;
Integer b = 10;

boolean numeric = (a + 0) == b; // true: a + 0 là int; b được unbox
```

Trong ví dụ này `a + 0` tạo `int` nên `==` cuối cùng là so sánh số học; còn `a == b` là so sánh tham chiếu. Tuy nhiên, đây không phải mẹo nên dùng để “ép equals”. Dùng `a.equals(b)` hoặc `Objects.equals(a,b)` khi muốn so sánh giá trị object, và kiểm tra null một cách rõ ràng.

## 10. Chương trình Java 17+ chạy độc lập

Tạo file **`WrapperEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("smallIdentity=" + (smallA == smallB));

        Integer largeA = 1_000;
        Integer largeB = 1_000;
        System.out.println("largeValuesEqual=" + largeA.equals(largeB));
        System.out.println("largePrimitiveEqual=" +
                (largeA.intValue() == largeB.intValue()));

        Integer alias = largeA;
        System.out.println("sameAlias=" + (largeA == alias));

        int primitive = 1_000;
        System.out.println("wrapperVsPrimitive=" + (largeA == primitive));
        long longPrimitive = 1_000L;
        System.out.println("wrapperVsLong=" + (largeA == longPrimitive));
        System.out.println("wrapperPlusZero=" + ((largeA + 0) == largeB));

        Integer missing = null;
        Integer alsoMissing = null;
        System.out.println("nullReferences=" + (missing == alsoMissing));
        System.out.println("nullLiteral=" + (missing == null));
        System.out.println("nullSafeEquals=" + Objects.equals(missing, alsoMissing));
        System.out.println("nullGuard=" + (missing != null && missing == 0));
        try {
            boolean outcome = (missing == 0);
            System.out.println("nullUnbox=" + outcome);
        } catch (NullPointerException ex) {
            System.out.println("nullUnbox=NullPointerException");
        }

        Integer numberInt = 7;
        Long numberLong = 7L;
        System.out.println("crossTypeEquals=" + numberInt.equals(numberLong));
        System.out.println("crossTypeNumeric=" +
                (numberInt.longValue() == numberLong.longValue()));

        Set<Integer> values = new HashSet<>();
        values.add(1_000);
        values.add(1_000);
        System.out.println("integerSetSize=" + values.size());

        Double plusZero = Double.valueOf(+0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("doubleWrapperEquals=" + plusZero.equals(minusZero));
        System.out.println("doublePrimitiveCompare=" + (minusZero == +0.0));

        Set<Double> zeros = new HashSet<>();
        zeros.add(+0.0);
        zeros.add(-0.0);
        System.out.println("doubleSetSize=" + zeros.size());

        double nan = Double.NaN;
        System.out.println("nanPrimitiveSelf=" + (nan == nan));
        System.out.println("nanWrapperEquals=" +
                Double.valueOf(nan).equals(Double.valueOf(nan)));

        long big = 9_007_199_254_740_993L;
        double rounded = 9_007_199_254_740_992.0;
        System.out.println("longDoubleNumericEqual=" + (big == rounded));
    }
}
```

Biên dịch và chạy:

```bash
javac WrapperEqualityDemo.java
java WrapperEqualityDemo
```

Kết quả chính xác:

```text
smallIdentity=true
largeValuesEqual=true
largePrimitiveEqual=true
sameAlias=true
wrapperVsPrimitive=true
wrapperVsLong=true
wrapperPlusZero=true
nullReferences=true
nullLiteral=true
nullSafeEquals=true
nullGuard=false
nullUnbox=NullPointerException
crossTypeEquals=false
crossTypeNumeric=true
integerSetSize=1
doubleWrapperEquals=false
doublePrimitiveCompare=true
doubleSetSize=2
nanPrimitiveSelf=false
nanWrapperEquals=true
longDoubleNumericEqual=true
```

Chương trình **không in `largeA == largeB`**, vì với các giá trị ngoài miền cache bảo đảm, identity của hai wrapper tạo riêng không phải một hợp đồng ổn định để kiểm thử. Các dòng `largeValuesEqual` và `wrapperVsPrimitive` mới là ngữ nghĩa đáng dựa vào trong bài toán so sánh **giá trị**.

## 11. Sai lầm thường gặp và cách khắc phục

| Phát biểu hoặc cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “Hai `Integer` dùng `==` là so sánh số.” | Sai: hai wrapper tham chiếu cùng kiểu dùng reference identity. | Dùng `equals` hoặc `Objects.equals`. |
| “`Integer 100 == Integer 100` đúng nên mọi `Integer` so sánh `==` đều an toàn.” | Sai: boxing/cache khiến giá trị nhỏ thường dùng chung object. | Không dựa vào cache để kiểm tra giá trị. |
| “`Integer 1000 == Integer 1000` chắc chắn sai.” | Không có bảo đảm identity cho vùng này. | Không phụ thuộc kết quả `==`. |
| “`Integer a == int b` vẫn so sánh tham chiếu.” | Primitive khiến wrapper được unbox để so sánh số. | Nếu có null, kiểm tra trước. |
| “`null Integer == 0` là false.” | Sai: unboxing null ném NPE. | `a != null && a == 0`. |
| “`a.equals(b)` an toàn với `a == null`.” | Sai: gọi method trên null ném NPE. | `Objects.equals(a,b)`, hoặc validate null trước. |
| “`Integer.equals(Long)` cho true nếu cùng 7.” | Sai: wrapper khác class không bằng nhau. | Chuyển sang kiểu số phù hợp trước khi so sánh. |
| “Có thể viết `Integer a == Long b` để tự unbox cả hai.” | Không hợp lệ khi hai vế đều là wrapper số khác loại không so sánh tham chiếu được. | Unbox tường minh rồi so sánh. |
| “`Double.equals` giống primitive `==` với ±0.0.” | Sai: wrapper phân biệt zero có dấu. | Chọn quy tắc cần dùng; có thể chuẩn hóa zero. |
| “`==` hai object `Double` sẽ kiểm tra NaN bằng nhau như `equals`.” | Sai: `==` so sánh identity, còn `equals` có quy tắc riêng cho NaN. | Sử dụng `Double.isNaN`/`Double.equals` phù hợp. |
| “`HashSet<Integer>` dựa vào cache để gộp số trùng.” | Sai: tập dùng `equals`/`hashCode`. | Hiểu contract collection. |

### Quy trình đọc một biểu thức `==`

1. **Xem kiểu tĩnh của mỗi vế.** Hai wrapper cùng loại là hai tham chiếu; wrapper và primitive số sẽ kích hoạt unboxing và numeric comparison.
2. **Xem có thể null không.** Hai tham chiếu so sánh với nhau hoặc với `null` không nhất thiết unbox; wrapper so sánh primitive có thể NPE.
3. **Đừng lấy cache làm logic nghiệp vụ.** Object reuse không phải bằng nhau về số.
4. **Chọn API bằng nhau theo nhu cầu.** `equals` cho wrapper cùng loại; `Objects.equals` để xử lý null; primitive numeric comparison khi chủ đích so sánh giá trị số sau chuyển kiểu.
5. **Kiểm tra khác loại và số thực.** `Integer`/`Long` không tự tương đương trong `equals`; `Double` có NaN/signed-zero và việc chuyển `long` sang `double` có thể mất chính xác.
6. **Với collection, xem `equals` và `hashCode`**, không phỏng đoán từ kết quả `==` của hai wrapper.

**Ghi nhớ:** `Integer == Integer` so sánh **identity**; `Integer == int` so sánh **giá trị sau unboxing**; `Integer.equals(Integer)` so sánh **giá trị trong cùng loại wrapper**. `null` và các quy tắc số thực có thể thay đổi hành vi, nên luôn xác định kiểu của hai toán hạng trước khi dùng `==`.