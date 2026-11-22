# Sai lầm khi dùng `==` để so sánh hai wrapper trong Java

## 1. Vấn đề: hai số bằng nhau vẫn có thể không `==`

Java có các kiểu nguyên thủy (*primitive*) như `int`, `long`, `double`, `boolean`, và các **lớp bao (*wrapper*)** tương ứng: `Integer`, `Long`, `Double`, `Boolean`, v.v. Cách so sánh chúng phụ thuộc **kiểu tĩnh của hai toán hạng** trong biểu thức, không chỉ phụ thuộc giá trị số hiển thị.

```java
int primitiveA = 1000;
int primitiveB = 1000;
System.out.println(primitiveA == primitiveB); // true: so sánh giá trị int

Integer boxA = Integer.valueOf(1000);
Integer boxB = Integer.valueOf(1000);
System.out.println(boxA.equals(boxB)); // true: hai giá trị Integer bằng nhau

// Tránh dùng boxA == boxB để quyết định giá trị số học bằng nhau:
// phép đó kiểm tra có phải cùng object hay không.
```

Các dòng trên là mảnh mã minh họa, đặt trong `main` của một lớp và không cần import `Integer`. Biểu thức `boxA == boxB` có thể trả `true` hoặc `false` tùy identity/caching; **không được xem là tiêu chí so sánh số**.

Trong bài này, ta sẽ:

- Hiểu `==` trên primitive, reference và wrapper.
- Nhận diện bẫy **Integer cache**, autoboxing, unboxing và trường hợp `null`.
- Chọn `equals()`, `Objects.equals()` và `compareTo()` đúng mục đích.
- Phân biệt wrapper khác loại như `Integer` với `Long`.
- Giải thích ngoại lệ `Double.NaN` và signed zero.
- Kiểm tra bằng các chương trình Java 17+ có đầu ra xác định.

## 2. Quy tắc nền tảng của `==`

Trong Java, `==` là toán tử **bằng nhau** và thực hiện so sánh theo loại toán hạng:

| Hai toán hạng | `==` có ý nghĩa gì? | Ví dụ |
|---|---|---|
| Hai giá trị primitive số | So sánh giá trị số sau quy tắc chuyển kiểu số | `10 == 10L` → `true` |
| Hai primitive `boolean` | So sánh giá trị logic | `true == true` → `true` |
| Hai tham chiếu kiểu có thể so sánh tham chiếu | So sánh **identity**: có cùng đối tượng hoặc đều null không | `Integer a, b; a == b` |
| Một wrapper số và một primitive số | Wrapper thường được **unbox**; sau đó so sánh số | `Integer a = 5; a == 5` → `true` |
| Wrapper khác loại không thể so sánh trực tiếp dưới quy tắc `==` tham chiếu | Có thể là **lỗi biên dịch**, ví dụ `Integer == Long` | Xem mục 6 |

Vì vậy, câu nói “`==` luôn so sánh địa chỉ” là **không đúng cho mọi biểu thức**. Nó đúng khi Java đang thực hiện **reference equality** giữa hai object. Nếu ít nhất một toán hạng là primitive số, Java có thể unbox wrapper rồi áp dụng **numeric equality**. Cần xem chính xác biểu thức được viết.

### Primitive và wrapper: khác kiểu dữ liệu

```java
int a = 200;
int b = 200;
System.out.println(a == b); // true

Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
System.out.println(x.equals(y)); // true
```

`int` không có identity đối tượng; `Integer` là reference type. Cả hai loại có thể cùng biểu diễn số 200 nhưng khác quy tắc so sánh mặc định.

## 3. Autoboxing, unboxing và Integer cache

### 3.1. Autoboxing là gì?

Java tự động chuyển primitive thành wrapper trong ngữ cảnh cần reference:

```java
Integer count = 10; // boxing từ int
int raw = count;    // unboxing trở về int
```

Về mặt ý nghĩa, boxing kiểu `int` được thực hiện tương tự `Integer.valueOf(10)`, không bắt buộc tạo đối tượng mới mỗi lần. JVM có thể dùng lại object wrapper theo cơ chế **cache**.

### 3.2. Vì sao `127 == 127` dạng `Integer` thường true?

Đối với `Integer.valueOf(int)`, Java **bảo đảm cache** các giá trị `-128` đến `127`, bao gồm hai đầu mút. Vì thế:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b);      // true: cùng object cache
System.out.println(a.equals(b)); // true: bằng giá trị
```

Kết quả `a == b` là `true` vì implementation trả về cùng tham chiếu đã cache; điều này không biến `==` thành phép so sánh giá trị.

Những wrapper khác cũng có cơ chế reuse theo hợp đồng:

- `Byte.valueOf`: cache toàn bộ miền `byte`.
- `Short.valueOf`, `Long.valueOf`: bảo đảm cache ít nhất `-128` đến `127`.
- `Character.valueOf`: cache ít nhất các ký tự mã `\u0000` đến `\u007F`.
- `Boolean.valueOf`: trả các đối tượng `Boolean.TRUE` hoặc `Boolean.FALSE`.
- `Float` và `Double`: **không có cam kết cache tương tự** cho các giá trị số; tránh suy luận identity.

Với `Integer` ở ngoài miền `-128..127`, Java **có thể mở rộng cache** tùy phiên bản JVM, cài đặt và cấu hình. Vì vậy, không viết test kiểu “`Integer.valueOf(128) == Integer.valueOf(128)` chắc chắn là false”.

### 3.3. Ví dụ đầy đủ với đầu ra ổn định

**Tệp `WrapperCacheDemo.java`:**

```java
public class WrapperCacheDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);

        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);

        System.out.println("smallSameReference=" + (smallA == smallB));
        System.out.println("smallSameValue=" + smallA.equals(smallB));
        System.out.println("largeSameValue=" + largeA.equals(largeB));
        System.out.println("largeViaCompareTo="
                + (largeA.compareTo(largeB) == 0));
    }
}
```

```bash
javac WrapperCacheDemo.java
java WrapperCacheDemo
```

```text
smallSameReference=true
smallSameValue=true
largeSameValue=true
largeViaCompareTo=true
```

Ví dụ **cố ý không in `largeA == largeB` như một kết quả cố định**, vì ở ngoài miền cache bắt buộc, identity phụ thuộc triển khai. Đừng xây quy tắc nghiệp vụ từ hiệu ứng cache dù có vẻ luôn đúng trên máy bạn.

## 4. `equals()` là phép so sánh giá trị của wrapper cùng loại

Các wrapper chuẩn triển khai `equals(Object)` để kiểm tra giá trị theo hợp đồng từng lớp, kèm yêu cầu kiểu đối tượng thích hợp.

```java
Integer x = Integer.valueOf(1_000);
Integer y = Integer.valueOf(1_000);
System.out.println(x.equals(y)); // true

Long a = Long.valueOf(1_000L);
Long b = Long.valueOf(1_000L);
System.out.println(a.equals(b)); // true

Boolean yes = Boolean.valueOf(true);
System.out.println(yes.equals(Boolean.TRUE)); // true
```

Đây là mảnh mã minh họa trong `main`. Với `Integer`, `Long`, `Short`, `Byte` và `Character`, `equals` xét **cùng loại wrapper và cùng giá trị tương ứng**. Nếu đối tượng khác loại thì không được coi là bằng nhau chỉ vì cùng biểu diễn số.

`equals` là instance method, nên:

```java
Integer maybe = null;
// maybe.equals(0); // Nếu chạy sẽ ném NullPointerException.
```

Khi dữ liệu có thể `null`, `Objects.equals(a,b)` có thể là lựa chọn thích hợp; xem mục 7.

### So sánh theo thứ tự bằng `compareTo()`

Khi cần nhỏ hơn/lớn hơn, wrapper số có thể dùng `compareTo` hoặc phương thức so sánh kiểu primitive:

```java
Integer x = 2;
Integer y = 10;

System.out.println(x.compareTo(y) < 0); // true
System.out.println(Integer.compare(x, y) < 0); // true
```

`Integer.compare(x,y)` nhận `int`, vì vậy sẽ unbox cả hai wrapper. Nó **không xử lý `null`**. Với `compareTo`, cũng tránh giả định kết quả nhất thiết chỉ là `-1`, `0`, `1`; hợp đồng so sánh dùng **dấu âm, zero hoặc dấu dương**.

## 5. Khi một bên là primitive: `==` có thể đúng giá trị nhưng gặp NPE

So sánh **một `Integer` với `int`** khiến Java unbox `Integer` rồi so sánh các giá trị primitive:

```java
Integer wrapper = Integer.valueOf(1_000);
int primitive = 1_000;
long wider = 1_000L;

System.out.println(wrapper == primitive); // true
System.out.println(wrapper == wider);     // true
```

Ở biểu thức thứ hai, `wrapper` được unbox từ `Integer` thành `int`, sau đó áp dụng binary numeric promotion để so với `long`. Đây là so sánh giá trị số, không phải so sánh identity của hai object.

**Nguy hiểm:** nếu wrapper là `null`, unboxing ném `NullPointerException`:

```java
Integer count = null;

System.out.println(count == null); // true: so sánh tham chiếu với null
// System.out.println(count == 0); // NullPointerException do unboxing
```

Sự khác biệt được quyết định bởi kiểu toán hạng thứ hai:

- `count == null`: so sánh reference, không unbox.
- `count == Integer.valueOf(0)`: hai reference kiểu `Integer`, so sánh identity, không unbox; nếu `count` null, kết quả `false`.
- `count == 0`: một bên primitive `int`, buộc unbox `count`; nếu null sẽ lỗi.
- `count > 0`, `count + 1`: đều cần unboxing, nên null cũng lỗi.

### Ví dụ đầy đủ: dự đoán trường hợp null

**Tệp `WrapperUnboxingDemo.java`:**

```java
public class WrapperUnboxingDemo {
    public static void main(String[] args) {
        Integer boxed = Integer.valueOf(1_000);
        int primitive = 1_000;
        long wide = 1_000L;

        System.out.println("boxVsInt=" + (boxed == primitive));
        System.out.println("boxVsLongPrimitive=" + (boxed == wide));

        Integer missing = null;
        Integer otherMissing = null;
        Integer one = Integer.valueOf(1);

        System.out.println("twoNullReferences=" + (missing == otherMissing));
        System.out.println("nullVsWrapper=" + (missing == one));
        System.out.println("nullLiteral=" + (missing == null));

        try {
            System.out.println(missing == 1);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NullPointerException");
        }
    }
}
```

```bash
javac WrapperUnboxingDemo.java
java WrapperUnboxingDemo
```

```text
boxVsInt=true
boxVsLongPrimitive=true
twoNullReferences=true
nullVsWrapper=false
nullLiteral=true
nullUnboxing=NullPointerException
```

Lưu ý: các phép `==` giữa hai tham chiếu null trả `true` vì **cùng giá trị tham chiếu null**, không phải vì hai object “bằng nhau”; ở đây không có object nào cả.

## 6. Hai wrapper khác loại: `Integer` và `Long`

Đây là bẫy quan trọng khác: hai wrapper có thể biểu diễn cùng giá trị số học nhưng **`equals` không cho true**:

```java
Integer i = Integer.valueOf(1);
Long l = Long.valueOf(1L);

System.out.println(i.equals(l)); // false: khác lớp
System.out.println(i.longValue() == l.longValue()); // true
```

**Không viết `i == l`** khi cả hai là object `Integer` và `Long`: biểu thức đó là **lỗi biên dịch** trong Java vì hai loại tham chiếu final này không có quan hệ chuyển kiểu cần thiết cho reference equality. Việc cả hai là `Number` **không tự biến `==` giữa chúng thành so sánh số học**.

Mã sau **chỉ để giải thích lỗi, không phải chương trình chạy được**:

```java
Integer i = 1;
Long l = 1L;
// boolean equal = (i == l); // LỖI BIÊN DỊCH: incomparable types
```

Nếu nghiệp vụ muốn so sánh **giá trị số học khác loại**, phải chọn cách chuẩn hóa có ý thức, ví dụ:

- Với `Integer` và `Long`, `i.longValue() == l.longValue()` bảo toàn chính xác cả hai miền, bởi `int` luôn chuyển chính xác sang `long`.
- Nếu liên quan `double`, `float` hoặc số nguyên rất lớn, chuyển sang floating-point có thể **mất chữ số**, nên cần tiêu chí và kiểu dữ liệu phù hợp (chẳng hạn `BigDecimal` được tạo đúng nguồn).
- Nếu nhu cầu là **bằng nhau về object và kiểu**, `Objects.equals(i,l)` trả `false` là hành vi hợp lý.

### Ví dụ đầy đủ

**Tệp `MixedWrapperDemo.java`:**

```java
public class MixedWrapperDemo {
    public static void main(String[] args) {
        Integer i = Integer.valueOf(1_000);
        Long l = Long.valueOf(1_000L);

        System.out.println("equals=" + i.equals(l));
        System.out.println("numeric=" + (i.longValue() == l.longValue()));
        System.out.println("againstPrimitiveLong=" + (i == 1_000L));
    }
}
```

```bash
javac MixedWrapperDemo.java
java MixedWrapperDemo
```

```text
equals=false
numeric=true
againstPrimitiveLong=true
```

Chỉ vì cùng chữ số `1000` không có nghĩa wrapper cùng kiểu hoặc cùng tham chiếu. Khi thiết kế API, hãy thống nhất một kiểu số phù hợp để tránh phải so sánh tùy tiện các wrapper khác loại.

## 7. `Objects.equals(a,b)`: xử lý null an toàn và dùng đúng `equals`

`java.util.Objects.equals(a,b)` kiểm tra hai tham chiếu đều null hoặc ủy quyền cho `a.equals(b)`. Nó tránh `NullPointerException` khi biến bên trái null:

```java
import java.util.Objects;

Integer a = null;
Integer b = null;
Integer one = 1;

System.out.println(Objects.equals(a, b)); // true
System.out.println(Objects.equals(a, one)); // false
System.out.println(Objects.equals(Integer.valueOf(500),
                                  Integer.valueOf(500))); // true
```

Đoạn mã trên minh họa trong `main`, với import đặt đầu tệp. `Objects.equals` **không tự quy đổi kiểu số**; `Objects.equals(Integer.valueOf(1), Long.valueOf(1L))` vẫn là `false`.

### Ví dụ hoàn chỉnh: bảng so sánh null-safe

**Tệp `WrapperObjectsEqualsDemo.java`:**

```java
import java.util.Objects;

public class WrapperObjectsEqualsDemo {
    public static void main(String[] args) {
        Integer a = null;
        Integer b = null;
        Integer x = Integer.valueOf(500);
        Integer y = Integer.valueOf(500);

        System.out.println("nullNull=" + Objects.equals(a, b));
        System.out.println("nullValue=" + Objects.equals(a, x));
        System.out.println("valueValue=" + Objects.equals(x, y));
        System.out.println("crossType=" + Objects.equals(
                Integer.valueOf(1), Long.valueOf(1L)));
    }
}
```

```bash
javac WrapperObjectsEqualsDemo.java
java WrapperObjectsEqualsDemo
```

```text
nullNull=true
nullValue=false
valueValue=true
crossType=false
```

**Quan trọng:** nếu `null` là dữ liệu không hợp lệ, `Objects.equals` không thay thế validation. Nó coi hai null là bằng nhau; với quy tắc nghiệp vụ đòi cả hai đều chứa số, hãy chủ động từ chối null trước khi so sánh.

## 8. `Double` và `Float`: `NaN`, signed zero còn gây khác biệt

Với wrapper số thực, `equals` không hoàn toàn giống phép `==` trên primitive. Điều này đặc biệt quan trọng khi bạn kiểm thử NaN và zero có dấu.

### 8.1. `NaN`: primitive không bằng chính nó, wrapper `equals` coi hai NaN bằng nhau

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN)));  // true
```

Ở dòng đầu, toán hạng là primitive `double` nên áp dụng so sánh IEEE 754: `NaN == NaN` luôn false. Dòng thứ hai dùng `Double.equals` trên hai wrapper; phương thức dựa vào quy tắc so sánh biểu diễn bit (chuẩn hóa các cách mã hóa NaN), nên hai giá trị NaN được xem là bằng nhau.

Vì vậy, nếu muốn kiểm tra một giá trị có phải NaN hay không, dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`; không dùng `== Double.NaN`.

### 8.2. `+0.0` và `-0.0`: primitive bằng nhau, wrapper `equals` phân biệt

```java
System.out.println(0.0 == -0.0); // true
System.out.println(Double.valueOf(0.0)
        .equals(Double.valueOf(-0.0))); // false
```

Hai zero bằng nhau theo so sánh số học primitive nhưng có bit dấu khác nhau. `Double.equals` phân biệt chúng, phù hợp với `Double.hashCode` và hành vi các collections phụ thuộc hash/equality.

`Double.compare(0.0, -0.0) > 0` cũng là `true`: API áp dụng thứ tự có phân biệt zero có dấu. Không suy ra rằng `Double.compare` luôn tương đương `==` của primitive.

### 8.3. Chương trình đầy đủ

**Tệp `FloatingWrapperEqualityDemo.java`:**

```java
public class FloatingWrapperEqualityDemo {
    public static void main(String[] args) {
        Double nanA = Double.valueOf(Double.NaN);
        Double nanB = Double.valueOf(Double.NaN);
        Double plusZero = Double.valueOf(0.0);
        Double minusZero = Double.valueOf(-0.0);

        System.out.println("primitiveNaN=" + (Double.NaN == Double.NaN));
        System.out.println("wrapperNaN=" + nanA.equals(nanB));
        System.out.println("primitiveZero=" + (0.0 == -0.0));
        System.out.println("wrapperZero=" + plusZero.equals(minusZero));
        System.out.println("compareZero=" + Double.compare(0.0, -0.0));
    }
}
```

```bash
javac FloatingWrapperEqualityDemo.java
java FloatingWrapperEqualityDemo
```

```text
primitiveNaN=false
wrapperNaN=true
primitiveZero=true
wrapperZero=false
compareZero=1
```

Tương tự, `Float` có quy tắc phù hợp cho `Float.NaN` và zero có dấu. Không dùng `==` để làm tiêu chí đồng nhất của mọi trường hợp floating-point mà không xét mục tiêu: so sánh số học, đồng nhất biểu diễn hay chính sách dung sai.

## 9. Vì sao lỗi này ảnh hưởng `HashSet` và `HashMap`?

`HashSet` và khóa của `HashMap` dùng `equals` cùng `hashCode` để xác định sự trùng lặp; chúng **không dựa trên `==` để so sánh giá trị wrapper**.

Ví dụ:

**Tệp `WrapperCollectionDemo.java`:**

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class WrapperCollectionDemo {
    public static void main(String[] args) {
        Set<Integer> ids = new HashSet<>();
        ids.add(Integer.valueOf(1_000));
        ids.add(Integer.valueOf(1_000));

        Map<Integer, String> byId = new HashMap<>();
        byId.put(Integer.valueOf(1_000), "first");
        byId.put(Integer.valueOf(1_000), "updated");

        System.out.println("setSize=" + ids.size());
        System.out.println("mapSize=" + byId.size());
        System.out.println("value=" + byId.get(Integer.valueOf(1_000)));
    }
}
```

```bash
javac WrapperCollectionDemo.java
java WrapperCollectionDemo
```

```text
setSize=1
mapSize=1
value=updated
```

Dù wrapper 1000 có thể được tạo thành các object khác nhau, chúng bằng nhau theo `Integer.equals`. `HashSet` giữ một phần tử và `HashMap` thay thế value của khóa cùng giá trị.

Nếu tự viết thuật toán khử trùng lặp với `==` trên wrapper, chương trình có thể hoạt động “đúng” ở vài giá trị nhỏ do cache rồi sai với đầu vào lớn hơn. Đừng sử dụng tính chất cache làm kiểm tra tính duy nhất.

## 10. Mẫu code thường sai và cách sửa

| Mục đích | Dễ viết sai | Cách nên dùng |
|---|---|---|
| Hai `Integer` bằng giá trị? | `a == b` | `a.equals(b)` nếu chắc chắn non-null |
| Hai wrapper cùng loại có thể null? | `a.equals(b)` | `Objects.equals(a,b)` |
| So sánh `Integer` lớn nhỏ | `a == b` | `a.compareTo(b) < 0`, `> 0`, `== 0` |
| `Integer` và `Long` cùng giá trị? | `a == b` (lỗi biên dịch) | `a.longValue() == b.longValue()` sau kiểm tra null |
| Wrapper với primitive | Mặc định không thể null | Validate null trước khi unbox |
| Kiểm tra `Double.NaN` | `x == Double.NaN` | `Double.isNaN(x)` |
| Phân biệt `+0.0` và `-0.0` kiểu `Double` | `x.doubleValue() == y.doubleValue()` | `x.equals(y)` hoặc so sánh bit phù hợp |
| Nhận biết cùng đối tượng? | `a.equals(b)` | `a == b` nếu identity thực sự là mục tiêu |
| Test equality dựa trên cache `Integer` | Kiểm tra `Integer.valueOf(128) == ...` với expected cứng | Kiểm tra `equals` cho giá trị, không dựa vào cache |

**Mẹo review:** khi thấy `==` xuất hiện giữa hai biến có tên `Integer`, `Long`, `Double`, `Boolean`, hãy đặt câu hỏi: “Mình có cần biết hai biến cùng tham chiếu không, hay cần so sánh giá trị?” Trong phần lớn nghiệp vụ xử lý số, câu trả lời là **giá trị**.

### Không dùng `new Integer(int)` để né cache

Constructor wrapper kiểu `new Integer(10)` đã bị deprecated và đánh dấu chờ loại bỏ ở Java hiện đại. Không dùng nó để ép “hai wrapper chắc chắn là hai object khác nhau” trong mã production hoặc test thông thường. Đây cũng là lý do các ví dụ ở bài ưu tiên `Integer.valueOf` và kiểm tra giá trị bằng `equals`.

## 11. Một ví dụ tổng hợp có thể chạy nguyên vẹn

Chương trình sau kiểm tra một loạt khác biệt bằng các đầu ra **không phụ thuộc cache ở ngoài miền bắt buộc**.

**Tệp `WrapperComparisonSummary.java`:**

```java
import java.util.Objects;

public class WrapperComparisonSummary {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);
        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);

        System.out.println("cache127=" + (smallA == smallB));
        System.out.println("equals1000=" + largeA.equals(largeB));
        System.out.println("numeric1000=" + (largeA == 1_000));

        Integer absent = null;
        System.out.println("nullEquals=" + Objects.equals(absent, null));

        Integer oneInt = Integer.valueOf(1);
        Long oneLong = Long.valueOf(1L);
        System.out.println("crossEquals=" + oneInt.equals(oneLong));
        System.out.println("crossNumeric="
                + (oneInt.longValue() == oneLong.longValue()));

        System.out.println("NaNprimitive=" + (Double.NaN == Double.NaN));
        System.out.println("NaNwrapper=" + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitive=" + (0.0 == -0.0));
        System.out.println("zeroWrapper=" + Double.valueOf(0.0)
                .equals(Double.valueOf(-0.0)));
    }
}
```

```bash
javac WrapperComparisonSummary.java
java WrapperComparisonSummary
```

```text
cache127=true
equals1000=true
numeric1000=true
nullEquals=true
crossEquals=false
crossNumeric=true
NaNprimitive=false
NaNwrapper=true
zeroPrimitive=true
zeroWrapper=false
```

Đầu ra `cache127=true` dựa trên cache được `Integer.valueOf` bảo đảm. Chương trình không coi identity của wrapper 1000 là điều kiện đúng/sai, vì nó không thuộc miền cache bắt buộc. `numeric1000` là so sánh `Integer` với literal **primitive** `int` nên unbox.

## 12. Kiểm thử để bắt lỗi `==` trên wrapper

Một số test thực dụng cho dự án xử lý wrapper:

1. **Vượt cache**: kiểm tra equality của `Integer.valueOf(1000)` và một `Integer` khác cùng giá trị qua `equals`, không cố gán expected cho `==`.
2. **Giá trị sát biên cache**: `127`, `128`, `-128`, `-129` giúp nhận diện sự khác nhau giữa identity và value; các ca ngoài miền cache phải kiểm tra theo hợp đồng, không dựa vào kết quả máy riêng.
3. **Null**: `null == null`, `Objects.equals(null, value)`, unboxing null khi so với primitive để xác nhận xử lý lỗi đúng.
4. **Kiểu khác nhau**: `Integer.valueOf(1).equals(Long.valueOf(1))` là `false`, còn so sánh giá trị qua kiểu chung có thể là `true`.
5. **Số thực đặc biệt**: `NaN`, `+0.0`, `-0.0` với primitive `==` và wrapper `equals`.
6. **Collections**: hai wrapper cùng giá trị ngoài cache được `HashSet`/khóa `HashMap` gộp đúng theo `equals/hashCode`.
7. **Không phụ thuộc JVM cache mở rộng**: test nên chạy ổn trên các JDK khác nhau, không đặt kỳ vọng giả rằng `Integer.valueOf(128) == Integer.valueOf(128)` nhất định là `false`.

Nếu kiểm tra biến thể null trong code có unboxing, hãy dùng bài test xác nhận nó **được từ chối đúng hoặc được xử lý trước khi unbox**. Không viết unit test chỉ so sánh vài giá trị trong miền cache rồi kết luận tính đúng cho mọi `Integer`.

## 13. Bài tập tự kiểm tra có lời giải

1. **`Integer a = 127, b = 127; a == b` có thể là gì?**  
   `true` theo bảo đảm boxing/cache cho các giá trị thuộc `-128..127`. Nhưng đây vẫn là phép so sánh reference.

2. **`Integer a = 1_000, b = 1_000; a == b` có phải luôn `false` không?**  
   Không thể khẳng định. Cache có thể được mở rộng; đừng dùng `==` để so sánh giá trị. `a.equals(b)` trả `true`.

3. **Vì sao `Integer a = null; a == 0` ném ngoại lệ, còn `a == null` không?**  
   `a == 0` cần unbox `a` thành `int`; null không thể unbox. `a == null` so sánh tham chiếu.

4. **`Integer.valueOf(3).equals(Long.valueOf(3L))` trả gì?**  
   `false`; hai đối tượng thuộc các lớp wrapper khác nhau.

5. **Có thể viết trực tiếp `Integer i; Long l; i == l` không?**  
   Không; hai wrapper final khác loại không so sánh được bằng toán tử reference `==` ở đây. Nếu cần, dùng cách so sánh số học có chuyển kiểu an toàn.

6. **`Double.NaN == Double.NaN` và `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả gì?**  
   Lần lượt `false` và `true` vì primitive `double` và `Double.equals` có hợp đồng khác nhau.

7. **`0.0 == -0.0` và `Double.valueOf(0.0).equals(Double.valueOf(-0.0))` trả gì?**  
   Lần lượt `true` và `false`; wrapper `equals` phân biệt bit dấu của zero.

8. **`Objects.equals(null,null)` có `true` không?**  
   Có. Tuy nhiên, nếu trường số bắt buộc phải có giá trị, cần kiểm tra validation riêng.

## 14. Kết luận và tài liệu tham khảo

Khi hai biến là **wrapper**, `==` có thể kiểm tra **cùng reference**, không phải số học. Kết quả đúng ở giá trị nhỏ có thể là do **cache**, và so sánh wrapper với primitive lại **unbox**. Để kiểm tra **hai wrapper cùng loại bằng giá trị**, dùng `equals` hoặc `Objects.equals` nếu cần hỗ trợ null; dùng `compareTo`/API so sánh thích hợp khi cần thứ tự. Với `Double`/`Float`, xác định rõ mục tiêu khi gặp `NaN` hoặc signed zero.

Tài liệu chính thức:

- [Java 21 — `Integer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [Java 21 — `Double`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [Java 21 — `Objects`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html)
- [Java Language Specification — Equality Operators, §15.21](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21)
- [Java Language Specification — Boxing Conversion, §5.1.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7)
