# Phân biệt so sánh giá trị với so sánh tham chiếu trong Java

> **Java core — language-basics / So sánh**  
> **Phiên bản:** Java 17+; một chương trình độc lập, không dùng thư viện ngoài.  
> **Mục tiêu:** Hiểu `==` so sánh **giá trị của kiểu nguyên thủy** nhưng so sánh **danh tính đối tượng** khi hai toán hạng là tham chiếu; chọn `equals()`, `Objects.equals()` hoặc API so sánh mảng phù hợp để kiểm tra nội dung.

## 1. Câu hỏi khác nhau: bằng giá trị hay cùng đối tượng?

Trong Java, có hai kiểu câu hỏi:

- **Bằng giá trị:** Hai số có bằng nhau không? Hai chuỗi có cùng ký tự không? Hai đối tượng có được coi là tương đương theo quy tắc của lớp không?
- **Cùng tham chiếu:** Hai biến tham chiếu có cùng trỏ tới **chính một đối tượng** trong bộ nhớ không?

~~~java
int x = 42;
int y = 42;
System.out.println(x == y); // true: so sánh giá trị int.

String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false: hai đối tượng khác nhau.
System.out.println(a.equals(b)); // true: cùng nội dung.
~~~

`a == b` không tự động so từng ký tự của chuỗi. Với cả hai toán hạng thuộc **kiểu tham chiếu**, `==` trả `true` khi cùng tham chiếu (hoặc cả hai `null`), chứ không phải khi nội dung giống nhau.

## 2. `==` và `!=` với kiểu nguyên thủy

Với các toán hạng nguyên thủy thích hợp, `==` và `!=` xét **giá trị**, có áp dụng quy tắc chuyển kiểu số khi so sánh:

~~~java
int a = 10;
long b = 10L;
boolean equal = (a == b);  // true: so sánh số.
boolean unequal = (a != b); // false.

boolean ready = true;
boolean enabled = true;
boolean sameFlag = ready == enabled; // true.
~~~

| Kiểu toán hạng | `==` có ý nghĩa gì? | Ví dụ |
| --- | --- | --- |
| `int`, `long`, `char`, ... | So sánh giá trị số sau chuyển kiểu phù hợp | `10 == 10L` → `true` |
| `boolean` | So sánh giá trị logic | `true == false` → `false` |
| `float`, `double` | So sánh giá trị số thực theo quy tắc dấu phẩy động | `0.0 == -0.0` → `true` |
| Hai tham chiếu có thể so sánh | So sánh có phải cùng đối tượng hoặc cùng `null` | `new Object() == new Object()` → `false` |

**Ngoại lệ cần biết với số thực:** `Double.NaN == Double.NaN` là `false`, dù cả hai biểu thức đều cho `NaN`. Dùng `Double.isNaN(...)` để kiểm tra NaN. So sánh trực tiếp hai số thực có kết quả tính toán thường cần cân nhắc sai số làm tròn.

`==` không hợp lệ để so sánh hai kiểu không tương thích, ví dụ không thể viết `"1" == 1`.

## 3. `==` trên tham chiếu: cùng object, không phải cùng nội dung

~~~java
String first = new String("hello");
String alias = first;
String second = new String("hello");

System.out.println(first == alias);  // true: alias cùng object.
System.out.println(first == second); // false: hai object riêng.
System.out.println(first.equals(second)); // true: cùng nội dung.
~~~

Một phép gán tham chiếu đơn thuần không tạo đối tượng mới: `alias = first` sao chép **giá trị tham chiếu**. Thay đổi trạng thái của một object có thể nhìn thấy qua các alias; còn gán lại biến tham chiếu không thay đổi biến kia.

Điều này đặc biệt quan trọng với các object có trạng thái thay đổi được, như mảng hoặc một lớp tự viết. Đừng dùng `==` để quyết định hai đối tượng “có cùng dữ liệu” trừ khi **danh tính đối tượng** chính là yêu cầu.

## 4. `equals()` và `Objects.equals()`: so sánh theo ngữ nghĩa của lớp

`equals(Object)` là một phương thức của `Object`. Nhưng kết quả phụ thuộc vào cách lớp triển khai:

- `Object.equals()` mặc định về cơ bản kiểm tra **cùng tham chiếu**.
- `String.equals()` so sánh **chuỗi ký tự**.
- Các lớp giá trị hoặc `record` có thể định nghĩa so sánh theo **thành phần dữ liệu**.
- Một lớp tự tạo **không override `equals()`** thì hai instance khác nhau vẫn có thể `equals() == false` dù field giống nhau.

~~~java
record Point(int x, int y) {}

Point p = new Point(2, 3);
Point q = new Point(2, 3);

System.out.println(p == q);      // false: hai đối tượng riêng.
System.out.println(p.equals(q)); // true: record so sánh thành phần.
~~~

Khi cần so sánh có thể gặp `null`, dùng `java.util.Objects.equals(a, b)`:

~~~java
import java.util.Objects;

// Trong một phương thức:
String a = null;
String b = null;

boolean bothMissing = Objects.equals(a, b); // true.
boolean missingVsText = Objects.equals(a, "Java"); // false.
~~~

`Objects.equals(a, b)` trả `true` nếu cả hai null, `false` nếu chỉ một null, và nếu cả hai không null thì dùng `a.equals(b)`. Điều này **không tự biến `equals` của lớp thành phép so sánh nội dung**; nó chỉ bảo vệ khỏi gọi method trên tham chiếu null.

## 5. Bẫy `String` literal và string pool

Java lưu các string literal và một số chuỗi hằng ở string pool. Bởi vậy đôi khi `==` trên chuỗi lại ra `true`, dễ khiến người học tưởng rằng `==` là phép so sánh nội dung:

~~~java
String a = "Java";
String b = "Ja" + "va"; // Biểu thức hằng: có thể gộp thành cùng literal.
String c = new String("Java");

System.out.println(a == b); // true: cùng tham chiếu tới chuỗi intern.
System.out.println(a == c); // false: new tạo String riêng.
System.out.println(a.equals(c)); // true: cùng ký tự.
~~~

**Không dựa vào string pool để kiểm tra dữ liệu người dùng.** Chuỗi đọc từ file, tham số, API hoặc được tạo trong runtime không bảo đảm dùng cùng tham chiếu chỉ vì có nội dung giống nhau.

Quy tắc tốt: muốn biết hai chuỗi có cùng văn bản, dùng `a.equals(b)` khi `a` chắc chắn không null, `"Java".equals(a)` khi so với hằng, hoặc `Objects.equals(a, b)` khi cả hai có thể null.

## 6. Lớp bao (`Integer`, `Boolean`...) và autoboxing

Lớp bao chứa giá trị nguyên thủy nhưng bản thân biến `Integer` là **tham chiếu**.

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true: hai giá trị int bằng nhau.
~~~

**Đừng dựa vào `a == b` để so sánh giá trị hai wrapper.** Các giá trị nhỏ có thể dùng cache, nhưng danh tính instance phụ thuộc cách tạo/cache; kết quả `==` dễ khác nhau trong các tình huống khác nhau.

Khi một bên là primitive và một bên là wrapper tương ứng, Java có thể **unbox** wrapper để so sánh giá trị:

~~~java
Integer wrapped = Integer.valueOf(1000);
int primitive = 1000;
System.out.println(wrapped == primitive); // true: unbox rồi so sánh số.
~~~

Nhưng unboxing tham chiếu `null` gây `NullPointerException`:

~~~java
Integer missing = null;
// boolean equal = (missing == 0); // NPE khi chạy.
boolean safe = Objects.equals(missing, Integer.valueOf(0)); // false.
~~~

Phân biệt **hai wrapper** (thường so sánh tham chiếu qua `==`) với **wrapper so primitive** (có thể unbox rồi so sánh giá trị). Đây là lỗi rất dễ xuất hiện khi đổi kiểu tham số hoặc dùng generics.

## 7. Mảng: `==`, `equals()` và `Arrays.equals()`

Mảng là object. Hai mảng khác nhau có cùng phần tử vẫn không phải cùng object:

~~~java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);              // false.
System.out.println(first.equals(second));         // false.
System.out.println(java.util.Arrays.equals(first, second)); // true.
~~~

Mảng **không override** `Object.equals()` để so sánh phần tử. Sử dụng `Arrays.equals` cho mảng một chiều; với mảng lồng nhau, `Arrays.deepEquals` có thể so sánh nội dung mảng con:

~~~java
int[][] a = {{1, 2}};
int[][] b = {{1, 2}};
System.out.println(java.util.Arrays.equals(a, b)); // false: inner arrays riêng.
System.out.println(java.util.Arrays.deepEquals(a, b)); // true.
~~~

Bảng chọn nhanh:

| Dữ liệu cần so sánh | Nên dùng | Tránh hiểu nhầm |
| --- | --- | --- |
| Hai `int`/`boolean` | `==` hoặc `!=` | Đây là so sánh giá trị primitive |
| Hai tham chiếu, cần kiểm tra cùng object | `==` | Không đại diện cho cùng nội dung |
| Hai `String`, có thể không null | `equals()` | `==` dễ bị ảnh hưởng bởi intern/string pool |
| Hai object nullable | `Objects.equals(a, b)` | Vẫn phụ thuộc `equals` của lớp |
| Hai mảng primitive một chiều | `Arrays.equals(a, b)` | Mảng kế thừa `Object.equals` |
| Hai mảng đa chiều | `Arrays.deepEquals(a, b)` | `Arrays.equals` chỉ so phần tử cấp trực tiếp |
| Hai object của lớp tự định nghĩa | `equals()` được override đúng hợp đồng | Mặc định `Object.equals()` là identity |

Nếu tự override `equals()`, hãy override cả `hashCode()` theo cùng logic để giữ hợp đồng trong `HashSet`/`HashMap`. `record` là lựa chọn hữu ích cho dữ liệu bất biến đơn giản; riêng thành phần kiểu mảng trong record không tự động được deep compare.

## 8. Chương trình Java 17+ runnable

Tạo file **ValueVsReferenceDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class ValueVsReferenceDemo {
    record Point(int x, int y) {}

    static final class Box {
        final int value;
        Box(int value) { this.value = value; }
    }

    public static void main(String[] args) {
        int x = 42;
        int y = 42;
        System.out.println("primitiveEqual=" + (x == y));

        String literal = "Java";
        String constant = "Ja" + "va";
        String created = new String("Java");
        String alias = created;
        System.out.println("literalSame=" + (literal == constant));
        System.out.println("literalVsCreated=" + (literal == created));
        System.out.println("createdAlias=" + (created == alias));
        System.out.println("stringValue=" + literal.equals(created));

        String missing = null;
        System.out.println("bothNull=" + Objects.equals(missing, null));
        System.out.println("nullVsText=" + Objects.equals(missing, literal));
        System.out.println("literalEqualsNull=" + "Java".equals(missing));

        Integer boxed = Integer.valueOf(1000);
        Integer anotherBoxed = Integer.valueOf(1000);
        int primitive = 1000;
        System.out.println("wrapperValue=" + boxed.equals(anotherBoxed));
        System.out.println("wrapperVsPrimitive=" + (boxed == primitive));
        Integer absent = null;
        try {
            System.out.println("unsafe=" + (absent == 0));
        } catch (NullPointerException ex) {
            System.out.println("wrapperNull=NullPointerException");
        }

        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        System.out.println("arrayIdentity=" + (a == b));
        System.out.println("arrayDefaultEquals=" + a.equals(b));
        System.out.println("arrayContent=" + Arrays.equals(a, b));

        int[][] grid1 = {{1, 2}};
        int[][] grid2 = {{1, 2}};
        System.out.println("nestedShallow=" + Arrays.equals(grid1, grid2));
        System.out.println("nestedDeep=" + Arrays.deepEquals(grid1, grid2));

        Box first = new Box(7);
        Box second = new Box(7);
        System.out.println("plainObjectEquals=" + first.equals(second));

        Point p = new Point(2, 3);
        Point q = new Point(2, 3);
        System.out.println("recordIdentity=" + (p == q));
        System.out.println("recordValue=" + p.equals(q));
        System.out.println("recordHashEqual=" + (p.hashCode() == q.hashCode()));

        double nan = Double.NaN;
        System.out.println("nanPrimitiveEqual=" + (nan == nan));
        System.out.println("nanDetected=" + Double.isNaN(nan));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ValueVsReferenceDemo.java
java ValueVsReferenceDemo
~~~

**Expected stdout chính xác:**

~~~text
primitiveEqual=true
literalSame=true
literalVsCreated=false
createdAlias=true
stringValue=true
bothNull=true
nullVsText=false
literalEqualsNull=false
wrapperValue=true
wrapperVsPrimitive=true
wrapperNull=NullPointerException
arrayIdentity=false
arrayDefaultEquals=false
arrayContent=true
nestedShallow=false
nestedDeep=true
plainObjectEquals=false
recordIdentity=false
recordValue=true
recordHashEqual=true
nanPrimitiveEqual=false
nanDetected=true
~~~

Output cố ý không in `boxed == anotherBoxed` vì kết quả identity của hai wrapper tạo qua cache không nên dùng để kiểm tra giá trị. Ngược lại, chương trình kiểm tra rõ `boxed.equals(anotherBoxed)` và `boxed == primitive`; phép sau unbox và so sánh số.

## 9. Bài tập và nguyên tắc nhớ

**Bài 1.** Cho hai biến `int` có giá trị 5 và hai biến `String` cùng văn bản "5" nhưng được tạo bởi hai lệnh `new String("5")`. `==` đang hỏi điều gì trong từng trường hợp?

**Bài 2.** Viết đoạn so sánh chuỗi nullable bằng `Objects.equals`. Vì sao gọi `a.equals(b)` khi `a == null` không an toàn?

**Bài 3.** Tạo hai mảng `int[]` cùng phần tử. So sánh kết quả `a == b`, `a.equals(b)` và `Arrays.equals(a, b)`.

**Bài 4.** Khi `Integer wrapped = null;`, điều gì xảy ra với `wrapped == 0`? Phân biệt với `Objects.equals(wrapped, Integer.valueOf(0))`.

**Bài 5.** Tạo hai `record Point(int x, int y)` cùng tọa độ. So sánh `==` và `equals()`. Nếu viết class thông thường mà không override `equals()` thì sao?

### Ghi nhớ

**`==` so sánh giá trị với kiểu nguyên thủy, nhưng so sánh danh tính với hai tham chiếu.** `equals()` kiểm tra bằng nhau theo cách lớp định nghĩa; `Objects.equals()` hỗ trợ `null` an toàn. Với `String` dùng so sánh nội dung, với mảng dùng `Arrays.equals`/`Arrays.deepEquals`, và với lớp bao hãy nhớ bẫy cache/autoboxing. Chỉ dùng `==` trên tham chiếu khi thực sự muốn hỏi “có cùng object không?”.
