# `Integer`, `Long`, `Double`, `Boolean` và các lớp bao khác — Java 17+

Java có tám **kiểu nguyên thủy** (*primitive*) dùng để lưu giá trị như số, ký tự và đúng/sai. Mỗi primitive có một **lớp bao** (*wrapper class*) tương ứng trong gói `java.lang`. Wrapper là **kiểu tham chiếu**: biến có thể tham chiếu đối tượng wrapper hoặc mang giá trị `null`. Wrapper cho phép đưa giá trị nguyên thủy vào API làm việc với đối tượng, đặc biệt là các collection và generic.

~~~java
int count = 42;          // int: gia tri nguyen thuy.
Integer boxed = count;   // Integer: autoboxing.
int again = boxed;       // int: unboxing.
~~~

`Integer` không phải cách viết dài hơn của `int`: hai kiểu có **ngữ nghĩa khác nhau**, đặc biệt ở `null`, so sánh, đối tượng được tạo và chi phí boxing/unboxing.

## 1. Bảng đủ tám cặp primitive ↔ wrapper

| Primitive | Wrapper trong `java.lang` | Ví dụ |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 7)` |
| `short` | `Short` | `Short.valueOf((short) 300)` |
| `int` | `Integer` | `Integer.valueOf(42)` |
| `long` | `Long` | `Long.valueOf(9L)` |
| `float` | `Float` | `Float.valueOf(1.25f)` |
| `double` | `Double` | `Double.valueOf(3.5)` |
| `char` | `Character` | `Character.valueOf('J')` |
| `boolean` | `Boolean` | `Boolean.valueOf(true)` |

Một số điều cần nhớ:

- `int` và `Integer` là hai **kiểu khác nhau**; Java có thể tự chuyển giữa chúng trong ngữ cảnh phù hợp.
- Wrapper **bất biến**: không có phương thức thay đổi giá trị số/boolean/ký tự bên trong cùng một wrapper. Gán `boxed = 43` khiến biến tham chiếu kết quả boxing khác, không sửa nội dung đối tượng `Integer` cũ.
- `boolean`/`Boolean` không được ép thành số `0`/`1` bằng cast của Java. Muốn ánh xạ phải viết quy tắc, ví dụ `flag ? 1 : 0`.
- `Void` là lớp đặc biệt đại diện cho từ khóa `void` trong một số API phản chiếu, **không phải wrapper thứ chín chứa một giá trị primitive `void`**.

## 2. Java 17+ runnable: đủ wrapper, parsing, so sánh và `null`

Lưu tệp **`WrapperTypesDemo.java`** với mã nguồn sau:

~~~java
import java.util.List;

public class WrapperTypesDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;  // Autoboxing int -> Integer.
        int unboxed = boxed;        // Unboxing Integer -> int.
        System.out.println("primitive=" + primitive);
        System.out.println("boxedInteger=" + boxed);
        System.out.println("unboxedInteger=" + unboxed);

        Long large = Long.valueOf(9_000_000_000L);
        Double fraction = Double.valueOf(3.5);
        Boolean enabled = Boolean.TRUE;
        Byte small = Byte.valueOf((byte) 7);
        Short medium = Short.valueOf((short) 32_000);
        Float ratio = Float.valueOf(1.25f);
        Character letter = Character.valueOf('J');

        System.out.println("long=" + large);
        System.out.println("double=" + fraction);
        System.out.println("boolean=" + enabled);
        System.out.println("other=" + small + "," + medium
                + "," + ratio + "," + letter);

        int parsedInt = Integer.parseInt("123");
        long parsedLong = Long.parseLong("9000000000");
        double parsedDouble = Double.parseDouble("2.5");
        boolean parsedBoolean = Boolean.parseBoolean("TrUe");
        boolean otherBoolean = Boolean.parseBoolean("yes");
        Integer boxedFromText = Integer.valueOf("123");

        System.out.println("parsedInt=" + parsedInt);
        System.out.println("parsedLong=" + parsedLong);
        System.out.println("parsedDouble=" + parsedDouble);
        System.out.println("parsedBoolean=" + parsedBoolean);
        System.out.println("parsedOtherBoolean=" + otherBoolean);
        System.out.println("valueOfInt=" + boxedFromText);

        Integer left = Integer.valueOf(1_000);
        Integer right = Integer.valueOf(1_000);
        System.out.println("sameValue=" + left.equals(right));

        Integer cachedA = Integer.valueOf(100);
        Integer cachedB = Integer.valueOf(100);
        System.out.println("cached100SameObject=" + (cachedA == cachedB));
        System.out.println("compare=" + Integer.compare(10, 20));

        List<Integer> numbers = List.of(3, 5, 7);
        int total = 0;
        for (Integer number : numbers) {
            total += number; // Unboxing de cong voi int.
        }
        System.out.println("listSum=" + total);
        System.out.println("charIsLetter=" + Character.isLetter(letter));

        Integer maybe = null;
        System.out.println("nullWrapper=" + (maybe == null));
        int fallback = maybe == null ? 0 : maybe;
        System.out.println("nullableDefault=" + fallback);

        try {
            int invalid = maybe; // Unboxing null.
            System.out.println("unexpected=" + invalid);
        } catch (NullPointerException ex) {
            System.out.println("unboxingNull=NullPointerException");
        }

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            System.out.println("badNumber=NumberFormatException");
        }

        System.out.println("nanPrimitiveEqual="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapperEqual="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitiveEqual=" + (0.0 == -0.0));
        System.out.println("zeroWrapperEqual="
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) ở thư mục chứa file. Dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WrapperTypesDemo.java
java WrapperTypesDemo
~~~

**Expected output chính xác** của lệnh `java WrapperTypesDemo`:

~~~text
primitive=42
boxedInteger=42
unboxedInteger=42
long=9000000000
double=3.5
boolean=true
other=7,32000,1.25,J
parsedInt=123
parsedLong=9000000000
parsedDouble=2.5
parsedBoolean=true
parsedOtherBoolean=false
valueOfInt=123
sameValue=true
cached100SameObject=true
compare=-1
listSum=15
charIsLetter=true
nullWrapper=true
nullableDefault=0
unboxingNull=NullPointerException
badNumber=NumberFormatException
nanPrimitiveEqual=false
nanWrapperEqual=true
zeroPrimitiveEqual=true
zeroWrapperEqual=false
~~~

Hai lệnh kiểm tra phiên bản JDK in thông tin tùy môi trường; chúng không thuộc khối expected output trên.

## 3. Wrapper và primitive chuyển đổi qua boxing/unboxing

**Autoboxing** đóng gói giá trị nguyên thủy thành wrapper khi Java cho phép; **unboxing** lấy giá trị primitive tương ứng. Trong số học, unboxing có thể xảy ra mà không có lời gọi method rõ ràng:

~~~java
Integer object = 42;           // Boxing int -> Integer.
int value = object;            // Unboxing Integer -> int.
int next = object + 1;         // Unbox rồi cộng -> 43.
~~~

Một wrapper được phép chứa `null`; vì vậy `Integer missing = null; int n = missing;` **biên dịch được nhưng ném `NullPointerException` lúc chạy**. Kiểm tra null trước phép toán hoặc thiết kế hợp đồng dữ liệu bắt buộc, không tự gán mặc định 0 nếu “chưa có” khác “bằng 0”. Biến cục bộ chưa khởi tạo cũng không tự có giá trị `null`; chỉ các field/reference array elements mới được default theo quy tắc Java.

Bài chuyên boxing giải thích chi tiết overload, chuyển kiểu số học và thao tác `++`, còn bài unboxing null tập trung vào các biểu thức/điều kiện có thể gây NPE.


## 4. API chuyển đổi chuỗi: kiểu trả về phải rõ

Các lớp bao có cả factory trả wrapper và parser trả primitive:

| Biểu thức | Kiểu trả về |
| --- | --- |
| `Integer.parseInt("42")` | `int` |
| `Integer.valueOf("42")` | `Integer` |
| `Long.parseLong("42")` | `long` |
| `Double.parseDouble("2.5")` | `double` |
| `Boolean.parseBoolean("TrUe")` | `boolean` |
| `String.valueOf(42)` | `String` |

`Integer.parseInt("abc")` ném `NumberFormatException`; `Boolean.parseBoolean("yes")` lại trả `false`, nên phải **validate riêng** nếu API chỉ chấp nhận `true`/`false`. Khi gán `int` parser trả về vào `Integer`, Java boxing **sau** lời gọi; kiểu trả về của method không đổi. Bài `parseInt()/valueOf()` giải thích các overload/radix và bài `NumberFormatException` phân loại lỗi dữ liệu.


## 5. Giá trị wrapper khác identity của đối tượng

~~~java
Integer a = Integer.valueOf(1_000);
Integer b = Integer.valueOf(1_000);
System.out.println(a.equals(b)); // true.
~~~

Với hai tham chiếu `Integer`, `a == b` kiểm tra **identity**, không phải số bên trong. `Integer.valueOf(100)` được bảo đảm tái sử dụng wrapper ở vùng cache `-128..127`, nhưng không thể dựa vào `==` để so giá trị nói chung. Dùng `a.equals(b)` nếu `a` không null, hoặc `Objects.equals(a, b)` nếu hai phía có thể null. Khi so wrapper với **primitive**, Java có thể unbox, nên null lại gây NPE.

`Double.equals` và `Float.equals` còn có quy tắc khác phép `==` primitive: hai wrapper chứa `NaN` được xem là bằng nhau, trong khi `+0.0` và `-0.0` được `equals` phân biệt. Vì vậy phải chọn rõ semantics mong muốn. Bài equality phân tích trường hợp hỗn hợp, còn bài cache giải thích các vùng identity được bảo đảm cho từng wrapper.


## 6. Wrapper trong generic và collection

Generic như `List<T>` yêu cầu **kiểu tham chiếu**:

~~~java
import java.util.List;

List<Integer> scores = List.of(3, 5, 7); // Hop le.
// List<int> invalid;                    // Khong hop le.
~~~

Dùng `List<Integer>` vì phần tử là đối tượng `Integer`. Khi thêm một `int` vào `List<Integer>`, Java có thể boxing; khi lấy phần tử để tính toán `int`, Java có thể unboxing. `List.of(...)` tạo danh sách không thể thay đổi qua các thao tác thêm/xóa; nó **không cho phép phần tử null**.

So với mảng:

~~~java
int[] primitiveArray = new int[2];        // Cac phan tu mac dinh 0.
Integer[] wrapperArray = new Integer[2]; // Cac phan tu mac dinh null.
~~~

Nếu hiệu năng, bộ nhớ và tránh null là ưu tiên trong vòng lặp xử lý số lượng lớn, primitive array hoặc API primitive có thể phù hợp hơn việc boxing hàng loạt. Tuy nhiên, lựa chọn nên dựa vào yêu cầu thực tế và đo đạc khi cần, không mặc định wrapper luôn là lựa chọn sai.

## 7. Wrapper bất biến, biến tham chiếu vẫn có thể gán lại

Wrapper không cho phép sửa giá trị bên trong instance. Phép toán trên biến wrapper có thể unbox, tính toán, box rồi **gán một tham chiếu kết quả**; một biến khác giữ tham chiếu cũ không bị thay đổi:

~~~java
Integer count = 10;
Integer before = count;
count = count + 1;
System.out.println(count);  // 11
System.out.println(before); // 10
~~~

Khai báo `final Integer fixed = 10;` cấm **gán lại biến** nhưng không phải nguyên nhân khiến wrapper bất biến. Bài boxing phân tích riêng toán tử `++` và các chuyển đổi ngầm.

## 8. Tóm tắt lựa chọn kiểu theo tình huống

| Khi nào? | Kiểu phù hợp thường gặp | Cần nhớ |
| --- | --- | --- |
| Biến đếm/tính toán luôn có giá trị | `int`, `long`, `double` | Không có trạng thái null |
| Giá trị có thể chưa được cung cấp | `Integer`, `Long`, `Boolean` | Phải quy định ý nghĩa của null |
| Generic collection | `List<Integer>`, `Map<String, Long>` | Type argument cần kiểu tham chiếu |
| Parse số để tính toán | `Integer.parseInt`, `Double.parseDouble` | Parser trả primitive tương ứng |

`Boolean` có thể biểu diễn ba trạng thái `TRUE`, `FALSE` và `null` nếu hợp đồng dữ liệu thật sự cần. Đừng tự coi null là false hoặc 0. Bài cuối chương áp dụng các nguyên tắc này cho model, API, validation và hiệu năng.

## 9. Bài tập tự kiểm tra

1. **Ghép cặp:** Kiểu bao của `int`, `char`, `boolean` và `double` là gì?  
   *Đáp án:* `Integer`, `Character`, `Boolean` và `Double`.
2. **Boxing:** `Integer x = 7; int y = x;` gồm những bước nào?  
   *Đáp án:* Boxing `int -> Integer`, rồi unboxing `Integer -> int`.
3. **Null:** `Integer n = null; int x = n;` có biên dịch không, và chạy thế nào?  
   *Đáp án:* Biên dịch được; lúc chạy ném `NullPointerException` khi unboxing.
4. **Parsing:** `Integer.parseInt("12")` khác `Integer.valueOf("12")` ở điểm nào?  
   *Đáp án:* Phương thức đầu trả `int`, phương thức sau trả `Integer`.
5. **Boolean:** `Boolean.parseBoolean("YES")` trả gì?  
   *Đáp án:* `false`; chỉ chuỗi bằng `"true"` không phân biệt hoa/thường được coi là true.
6. **So sánh:** Vì sao không nên so hai biến `Integer` bằng `==`?  
   *Đáp án:* `==` kiểm tra đồng nhất đối tượng, có thể chịu tác động của cache; dùng `equals` để so giá trị khi không null.
7. **Số thực:** `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả gì?  
   *Đáp án:* `true` theo định nghĩa `Double.equals`, dù `Double.NaN == Double.NaN` là `false`.

## Checklist ghi nhớ

- [ ] Thuộc **tám cặp primitive–wrapper**, đặc biệt `char -> Character` và `int -> Integer`.
- [ ] Hiểu **autoboxing/unboxing** là chuyển đổi, không biến primitive thành reference vĩnh viễn.
- [ ] Biết wrapper có thể null và unboxing null gây `NullPointerException`.
- [ ] Dùng `parseXxx` khi muốn primitive; dùng `valueOf` khi muốn wrapper.
- [ ] Dùng `equals`/`Objects.equals` để so giá trị wrapper, không dựa vào `==` và cache.
- [ ] Nhận biết quy tắc riêng của `Double`/`Float` với `NaN` và zero có dấu.
- [ ] Biết generic như `List<Integer>` không chấp nhận kiểu tham số `int`.
- [ ] Chọn primitive cho dữ liệu luôn có giá trị, wrapper khi API/generic yêu cầu hoặc null là trạng thái có nghĩa.

**Kết luận:** Các lớp `Integer`, `Long`, `Double`, `Boolean`, `Byte`, `Short`, `Float` và `Character` giúp làm việc với giá trị primitive trong thế giới đối tượng của Java. Dùng chúng đúng nghĩa: **giữ rõ kiểu dữ liệu, xử lý null trước khi unboxing, phân biệt so sánh giá trị với tham chiếu, và chọn phương thức parsing/boxing phù hợp**.
