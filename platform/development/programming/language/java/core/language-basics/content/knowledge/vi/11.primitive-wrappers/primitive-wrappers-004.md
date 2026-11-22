# Phân biệt so sánh tham chiếu lớp bao với so sánh giá trị — Java 17+

Trong Java, các lớp bao (*wrapper classes*) như `Integer`, `Long`, `Double`, `Float`, `Boolean`, `Character`, `Byte`, `Short` là **kiểu tham chiếu** bao bọc các giá trị nguyên thủy. Vì vậy, hai câu hỏi sau **không giống nhau**:

1. **Hai biến có trỏ cùng một đối tượng không?** Dùng `==` khi hai toán hạng thực sự được so sánh dưới dạng tham chiếu.
2. **Hai đối tượng có giá trị bằng nhau theo quy tắc của lớp bao không?** Dùng `equals()` hoặc `Objects.equals()`, tùy việc có thể gặp `null`.

~~~java
Integer a = Integer.valueOf(100);
Integer b = Integer.valueOf(100);

System.out.println(a == b);      // true trong truong hop gia tri 100 duoc cache.
System.out.println(a.equals(b)); // true do gia tri bang nhau.
~~~

**Điểm quan trọng:** kết quả `a == b` là `true` **không phải vì `==` đã so giá trị số**. Đây là hệ quả của việc hai tham chiếu cùng trỏ một wrapper được dùng chung thông qua cơ chế cache.

## 1. Bảng phân biệt các phép so sánh

| Biểu thức | Ý nghĩa chính | Có an toàn với null không? |
| --- | --- | --- |
| `wrapperA == wrapperB` | So **đồng nhất tham chiếu** khi cả hai là wrapper tham chiếu cùng kiểu | Có, nếu chỉ so tham chiếu |
| `wrapperA.equals(wrapperB)` | So **giá trị wrapper** theo triển khai `equals` | Không nếu `wrapperA == null` |
| `Objects.equals(wrapperA, wrapperB)` | So bằng nhau, có xử lý hai vế `null` | Có |
| `intA == intB` | So giá trị primitive `int` | Primitive không nhận `null` |
| `wrapperA == intB` | Wrapper có thể được **unbox**, rồi so giá trị primitive | Không an toàn nếu wrapper là `null` |
| `Integer.compare(a, b)` | So thứ tự hai `int`, trả âm/0/dương | `a` và `b` là primitive |
| `wrapperA.compareTo(wrapperB)` | So thứ tự hai wrapper tương thích | Có thể ném NPE khi dùng null |

Java chọn quy tắc dựa trên **kiểu toán hạng**, không phải vì một bên “trông giống số”. Đặc biệt, `Integer == Integer` (hai wrapper) và `Integer == int` (một wrapper, một primitive) có thể dẫn đến **hai kiểu so sánh khác nhau**.

## 2. Ví dụ Java 17+ chạy được

Lưu thành tệp UTF-8 **`WrapperEqualityDemo.java`**:

~~~java
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(100);
        Integer smallB = Integer.valueOf(100);
        Integer alias = smallA;

        System.out.println("smallSameReference=" + (smallA == smallB));
        System.out.println("aliasSameReference=" + (alias == smallA));
        System.out.println("smallValueEqual=" + smallA.equals(smallB));

        Integer largeA = Integer.valueOf(1_000);
        Integer largeB = Integer.valueOf(1_000);
        System.out.println("largeValueEqual=" + largeA.equals(largeB));
        System.out.println("largeObjectsEqual="
                + Objects.equals(largeA, largeB));

        Integer integer42 = Integer.valueOf(42);
        Long long42 = Long.valueOf(42L);
        System.out.println("crossWrapperEquals="
                + integer42.equals(long42));
        System.out.println("compareOrder="
                + Integer.valueOf(5).compareTo(Integer.valueOf(9)));

        int primitive100 = 100;
        System.out.println("wrapperVsPrimitive="
                + (smallA == primitive100));
        System.out.println("equalsBoxedArgument="
                + smallA.equals(100));

        Integer missing = null;
        Integer alsoMissing = null;
        System.out.println("bothNullReferences="
                + (missing == alsoMissing));
        System.out.println("nullVsWrapper=" + (missing == smallA));
        System.out.println("bothNullObjects="
                + Objects.equals(missing, alsoMissing));
        System.out.println("mixedObjects="
                + Objects.equals(missing, smallA));
        System.out.println("knownEqualsNull=" + smallA.equals(missing));
        System.out.println("guardedCompare="
                + (missing != null && missing.intValue() == 100));

        try {
            System.out.println("dangerousCompare="
                    + (missing == primitive100));
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }

        try {
            System.out.println("dangerousEquals="
                    + missing.equals(smallA));
        } catch (NullPointerException ex) {
            System.out.println("equalsNull=NullPointerException");
        }

        System.out.println("nanPrimitive="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapper="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("signedZeroPrimitive=" + (0.0d == -0.0d));
        System.out.println("signedZeroWrapper="
                + Double.valueOf(0.0d)
                        .equals(Double.valueOf(-0.0d)));
        System.out.println("signedZeroCompare="
                + Double.compare(0.0d, -0.0d));

        System.out.println("booleanWrapper="
                + Boolean.TRUE.equals(Boolean.valueOf(true)));
        System.out.println("numericDifferentWrappers="
                + Double.valueOf(1.0).equals(Integer.valueOf(1)));
    }
}
~~~

Trong PowerShell (Windows) hoặc Bash (Linux/macOS), chạy tại thư mục có tệp bằng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WrapperEqualityDemo.java
java WrapperEqualityDemo
~~~

**Expected output chính xác của lệnh `java WrapperEqualityDemo`:**

~~~text
smallSameReference=true
aliasSameReference=true
smallValueEqual=true
largeValueEqual=true
largeObjectsEqual=true
crossWrapperEquals=false
compareOrder=-1
wrapperVsPrimitive=true
equalsBoxedArgument=true
bothNullReferences=true
nullVsWrapper=false
bothNullObjects=true
mixedObjects=false
knownEqualsNull=false
guardedCompare=false
unboxNull=NullPointerException
equalsNull=NullPointerException
nanPrimitive=false
nanWrapper=true
signedZeroPrimitive=true
signedZeroWrapper=false
signedZeroCompare=1
booleanWrapper=true
numericDifferentWrappers=false
~~~

Các lệnh kiểm tra `java -version` và `javac -version` có đầu ra tùy JDK, không thuộc khối expected output trên.

## 3. Cache chỉ là một nguyên nhân khiến phép `==` có vẻ đúng

`Integer.valueOf(int)` được bảo đảm tái sử dụng đối tượng cho các số từ **−128 đến 127**:

~~~java
Integer a = Integer.valueOf(100);
Integer b = Integer.valueOf(100);
System.out.println(a == b); // true, vì cùng đối tượng được cache.
~~~

Với giá trị ngoài vùng bắt buộc, ví dụ `1_000`, không nên công bố output cố định cho `Integer.valueOf(1000) == Integer.valueOf(1000)`; JVM có thể cache rộng hơn. `equals` mới là hợp đồng so giá trị ổn định. Bài kế tiếp giải thích riêng về phạm vi cache của `Byte`, `Short`, `Long`, `Character`, `Boolean` và những gì **không được bảo đảm** về object identity.


## 4. Khi một vế là primitive, `==` có thể kích hoạt unboxing

~~~java
Integer wrapper = Integer.valueOf(100);
int number = 100;
System.out.println(wrapper == number); // true.
~~~

Với `Integer == int`, Java có thể **unbox** wrapper thành `int` và áp dụng phép so số primitive. Vì vậy kết quả phản ánh giá trị số **nhưng chỉ sau khi unboxing**.

Nếu wrapper là `null`:

~~~java
Integer maybe = null;
int number = 100;

// boolean same = maybe == number;
// Runtime: NullPointerException khi unboxing maybe.
~~~

Ngược lại, phép so sau **không unbox** chỉ vì gặp `null` nếu cả hai toán hạng có kiểu tham chiếu cùng kiểu:

~~~java
Integer a = null;
Integer b = Integer.valueOf(100);

System.out.println(a == b); // false, khong NPE.
~~~

**Quy tắc nhớ:** hãy xem **kiểu tĩnh của cả hai toán hạng** trước khi giải thích `==`, và tránh những biểu thức so sánh gây unboxing một wrapper có thể null.

## 5. `equals()` của wrapper so cái gì?

Với `Integer`, phương thức `equals` trả `true` khi đối số là một **`Integer`** chứa cùng giá trị `int`:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
Long c = Long.valueOf(42L);

System.out.println(a.equals(b)); // true.
System.out.println(a.equals(c)); // false.
~~~

`Integer(42)` và `Long(42)` mang **giá trị toán học** tương ứng nhưng **không phải cùng kiểu wrapper**. `equals` của hai lớp không tự chuyển `Long` sang `Integer`.

Đối với `Double`/`Float`, còn có hai điểm đặc biệt:

| Cặp dữ liệu | So bằng primitive `==` | Wrapper `equals` |
| --- | --- | --- |
| `Double.NaN` và `Double.NaN` | `false` | `true` |
| `+0.0d` và `-0.0d` | `true` | `false` |

`Double.equals` dùng quy tắc bit của `Double.doubleToLongBits`: các biểu diễn NaN được chuẩn hóa khi kiểm tra bình đẳng, còn dấu của zero được phân biệt. `Float.equals` có cách xử lý tương tự. Vì thế **không thay thế tùy tiện** so sánh số thực primitive bằng `equals` nếu đặc tả bài toán cần quy tắc IEEE 754 của toán tử `==`.

Nếu muốn so thứ tự, `Integer.compare`, `Long.compare`, `Double.compare` hoặc `compareTo` có ngữ nghĩa khác với kiểm tra cùng tham chiếu. `Double.compare(+0.0, -0.0)` trả kết quả **dương**, như ví dụ.

## 6. `null`: cách so an toàn

**`equals` có thể ném NPE khi đối tượng nhận lời gọi là null:**

~~~java
Integer a = null;
Integer b = 10;

// a.equals(b); // NullPointerException.
System.out.println(Objects.equals(a, b)); // false.
~~~

`Objects.equals(a, b)` kiểm tra an toàn khi một hoặc cả hai biến có thể null; hai giá trị null được coi là bằng nhau. Tuy vậy, việc **“hai giá trị đều thiếu” có nên được coi là tương đương trong nghiệp vụ hay không** là quyết định riêng của ứng dụng.

| Yêu cầu | Cách viết | Ghi chú |
| --- | --- | --- |
| Wrapper biết chắc không null, cùng kiểu | `a.equals(b)` | So giá trị wrapper |
| Hai wrapper có thể null | `Objects.equals(a, b)` | Null-safe, dùng `equals` cho đối tượng |
| Một wrapper so với giá trị cố định | `Integer.valueOf(10).equals(a)` | Đối tượng nhận lời gọi chắc chắn khác null |
| Muốn so primitive và wrapper nullable | `a != null && a.intValue() == 10` | Kiểm tra null trước unboxing |
| Muốn thứ tự tăng/giảm | `Integer.compare(x, y)` | Dùng primitive; xử lý null trước nếu nguồn là wrapper |
| Muốn kiểm tra cùng đối tượng | `a == b` | Chỉ khi identity thật sự là mục tiêu |

**Không dùng `Objects.equals` như một phép so số học xuyên kiểu:** `Objects.equals(Integer.valueOf(1), Long.valueOf(1))` là `false` vì hai wrapper khác lớp.

## 7. Autoboxing, cache và toán tử gán lại

~~~java
Integer a = 7;
Integer b = a;

a = a + 1;
System.out.println(a); // 8.
System.out.println(b); // 7.
~~~

`a + 1` unbox `Integer` thành `int`, cộng thành 8, sau đó boxing kết quả để gán lại `a`. Wrapper bất biến: phép gán này **không sửa** đối tượng đang được `b` tham chiếu.

Cache là tối ưu hóa khả thi cho đối tượng bất biến; sự tồn tại của cache không làm `Integer` trở thành primitive. Đừng cố suy đoán số lượng đối tượng được cấp phát chỉ từ cú pháp boxing nếu không có kiểm chứng thực tế và không phải trọng tâm nghiệp vụ.

## 8. Bài tập tự kiểm tra

1. **Hai wrapper `Integer`:** `Integer a = 100, b = 100; a == b` trả gì?  
   *Đáp án:* `true` với autoboxing hằng 100 thuộc vùng cache bắt buộc; nhưng không dùng `==` như phép so giá trị nói chung.
2. **Wrapper lớn:** `Integer a = Integer.valueOf(1000); Integer b = Integer.valueOf(1000); a.equals(b)` trả gì?  
   *Đáp án:* `true`. Không cần giả định kết quả `a == b`.
3. **Khác loại:** `Integer.valueOf(42).equals(Long.valueOf(42L))` trả gì?  
   *Đáp án:* `false` vì đối số không phải `Integer`.
4. **Unboxing:** `Integer x = null; boolean same = (x == 10);` xảy ra gì?  
   *Đáp án:* Ném `NullPointerException` khi unbox `x`.
5. **Null-safe:** `Objects.equals(null, null)` và `Objects.equals(null, Integer.valueOf(1))` là gì?  
   *Đáp án:* Lần lượt `true` và `false`.
6. **NaN:** Tại sao `Double.NaN == Double.NaN` là false, còn `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là true?  
   *Đáp án:* Phép `==` primitive tuân theo quy tắc NaN số thực; wrapper `equals` áp dụng quy tắc bình đẳng trên biểu diễn bit đã chuẩn hóa NaN.
7. **Zero có dấu:** `Double.valueOf(0.0).equals(Double.valueOf(-0.0))` là gì?  
   *Đáp án:* `false`; wrapper phân biệt dấu của zero, dù `0.0 == -0.0` là `true`.

## Checklist

- [ ] Phân biệt **identity tham chiếu** với **bình đẳng giá trị wrapper**.
- [ ] Với hai wrapper cùng kiểu, `==` kiểm tra đối tượng; `equals` kiểm tra giá trị wrapper.
- [ ] Không dựa vào cache `Integer` để suy đoán kết quả của `==` cho mọi số.
- [ ] Khi wrapper so với primitive, kiểm tra nguy cơ **unboxing null**.
- [ ] Dùng `Objects.equals` khi hai wrapper có thể null.
- [ ] Không coi `Integer` và `Long` có giá trị bằng nhau là `equals` bằng nhau.
- [ ] Nhớ `Double`/`Float` khác biệt về `NaN` và `+0.0`/`-0.0`.
- [ ] Chọn `compare`/`compareTo` khi cần so thứ tự thay vì bình đẳng.

**Kết luận:** Muốn kiểm tra **cùng đối tượng**, hãy dùng `==` giữa tham chiếu và hiểu rõ cache. Muốn kiểm tra **cùng giá trị lớp bao**, dùng `equals` hoặc `Objects.equals` (nếu có null). Với một bên primitive, luôn xem xét **unboxing** trước khi tin rằng phép `==` an toàn.
