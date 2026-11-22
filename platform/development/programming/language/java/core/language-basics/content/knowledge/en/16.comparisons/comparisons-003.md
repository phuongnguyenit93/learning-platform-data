# So sánh `boolean` và giới hạn dùng toán tử quan hệ trong Java

> **Java core — language-basics / So sánh**  
> **Phiên bản:** Java 17+; ví dụ độc lập, chỉ cần JDK.  
> **Mục tiêu:** Biết dùng `==`, `!=` để so sánh hai giá trị `boolean`; hiểu vì sao `<`, `<=`, `>`, `>=` không dùng được với `boolean`; phân biệt phép so sánh với phép logic và xử lý đúng `Boolean` nullable.

## 1. `boolean` chỉ có hai giá trị

Kiểu nguyên thủy `boolean` biểu diễn điều kiện logic, với đúng hai giá trị `true` và `false`:

~~~java
boolean isReady = true;
boolean isDone = false;
~~~

`boolean` **không phải kiểu số nguyên** trong Java: không thể ngầm chuyển `true` thành 1, `false` thành 0 hoặc ngược lại. Vì vậy:

~~~java
// KHÔNG BIÊN DỊCH:
// boolean flag = 1;
// int number = true;
// boolean equal = (true == 1);
~~~

Không cần viết `if (isReady == true)` để kiểm tra điều kiện thông thường; `if (isReady)` dễ đọc hơn. Với phủ định, dùng `!isReady`.

## 2. `==` và `!=` hợp lệ với `boolean`

Hai toán tử bằng/khác áp dụng được cho **hai biểu thức kiểu `boolean`**:

~~~java
boolean a = true;
boolean b = false;

boolean same = (a == b);      // false
boolean different = (a != b); // true
boolean sameAsTrue = (a == true); // true, nhưng thường không cần viết dài.
~~~

| Vế trái | Vế phải | `a == b` | `a != b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `false` |
| `true` | `false` | `false` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `true` | `false` |

**Ý nghĩa:** `==` trả `true` nếu hai giá trị logic bằng nhau; `!=` trả `true` nếu khác nhau. Kết quả phép so sánh cũng có kiểu `boolean`, sử dụng được trong `if`, `while` hoặc trong phép logic khác.

## 3. Vì sao `<`, `<=`, `>`, `>=` không dùng với `boolean`?

Các toán tử **quan hệ** (relational operators) dùng để so sánh thứ tự của **giá trị số** trong Java, không nhận toán hạng `boolean`.

~~~java
// Các dòng sau là ví dụ SAI, cố ý comment để chương trình không lỗi:
// boolean smaller = false < true;
// boolean greater = true > false;
// boolean atLeast = true >= false;
// boolean atMost = false <= true;
~~~

Java không định nghĩa quy tắc kiểu primitive `false < true` hay `true > false`, dù một số ngôn ngữ khác có thể xem false/true như 0/1.

So sánh hợp lệ với các kiểu số và `char`:

~~~java
int minimum = 3, maximum = 7;
boolean less = minimum < maximum; // true
boolean range = minimum >= 0 && maximum <= 10; // true
boolean charOrder = 'A' < 'B'; // true: char tham gia so sánh theo giá trị ký tự.
~~~

| Toán tử | `int`, `long`, `float`, `double`, `char` | `boolean` |
| --- | --- | --- |
| `==`, `!=` | Hợp lệ | Hợp lệ |
| `<`, `<=` | Hợp lệ | **Không hợp lệ** |
| `>`, `>=` | Hợp lệ | **Không hợp lệ** |

Lưu ý: đây là bảng về **kiểu nguyên thủy**. `String` cũng không so sánh thứ tự bằng `<`/`>`; dùng `compareTo` hoặc `Comparator` phù hợp khi muốn sắp xếp chuỗi.

## 4. Phép so sánh khác phép logic

Sau khi có các giá trị `boolean`, ta có thể kết hợp hoặc đảo điều kiện bằng toán tử logic:

| Toán tử | Ý nghĩa với `boolean` | Có bỏ qua vế phải? |
| --- | --- | --- |
| `!a` | NOT: đảo `true`/`false` | Toán tử một ngôi |
| `a && b` | AND có short-circuit | Có, nếu `a` là `false` |
| `a \|\| b` | OR có short-circuit | Có, nếu `a` là `true` |
| `a & b` | AND không short-circuit | Không |
| `a \| b` | OR không short-circuit | Không |
| `a ^ b` | XOR, chỉ đúng khi khác nhau | Không |

~~~java
boolean ready = true;
boolean finished = false;

boolean allowed = ready && !finished; // true
boolean any = ready || finished;      // true
boolean exactlyOne = ready ^ finished; // true
~~~

`^` trên hai giá trị `boolean` có kết quả tương đương `!=` về **giá trị logic**, nhưng không nên thay lẫn tùy tiện vì mục đích diễn đạt có thể khác: `!=` nhấn mạnh **so sánh khác nhau**; `^` nhấn mạnh **XOR**. Với boolean, cả hai vế của `^` được đánh giá.

**Short-circuit rất quan trọng khi có `null` hoặc phép tính có thể lỗi:**

~~~java
String name = null;
boolean hasName = name != null && !name.isBlank(); // false, không NPE.
~~~

Vế phải bị bỏ qua vì điều kiện bên trái `false`. Viết ngược thành `!name.isBlank() && name != null` sẽ lỗi trước khi guard được áp dụng.

## 5. Khi cần thứ tự của hai giá trị logic, hãy chỉ định rõ

Đôi khi nghiệp vụ muốn sắp xếp `false` **trước** `true`, chẳng hạn khi sort một danh sách trạng thái. **Không** viết `false < true`.

Java có phương thức:

~~~java
int order = Boolean.compare(false, true); // -1
int equal = Boolean.compare(true, true);  // 0
int reverse = Boolean.compare(true, false); // 1
~~~

`Boolean.compare(a, b)` trả giá trị âm/0/dương khi a đứng trước/bằng/sau b trong thứ tự **false trước true**. Đây là **thứ tự do API định nghĩa**, không phải việc `<` trở thành toán tử hợp lệ đối với `boolean`.

Nếu nghiệp vụ cần đảo thứ tự, có thể hoán đổi hai tham số hoặc sử dụng `Comparator` theo yêu cầu; đừng mã hóa boolean thành số một cách tùy tiện rồi so sánh khi không cần thiết.

## 6. Phân biệt `boolean` và `Boolean`

`boolean` là kiểu nguyên thủy **không thể là `null`**. `Boolean` là lớp bao tham chiếu; một biến `Boolean` có thể nhận `true`, `false` hoặc `null`:

~~~java
boolean primitive = true;
Boolean boxed = Boolean.TRUE;
Boolean unknown = null;
~~~

Có ba bẫy cần nhớ:

**(1) So sánh hai `Boolean` bằng `==` có thể so sánh tham chiếu.**

Khi cả hai toán hạng đều thuộc kiểu tham chiếu `Boolean`, `==` là phép so sánh **cùng object**; đừng dùng nó để đảm bảo so sánh **giá trị** trong mọi trường hợp. Dùng `equals` hoặc `Objects.equals` khi cần so sánh giá trị, kể cả nullable:

~~~java
import java.util.Objects;

// Trong một phương thức:
Boolean first = Boolean.TRUE;
Boolean second = Boolean.TRUE;
boolean sameValue = Objects.equals(first, second); // true
~~~

Không dựa vào kết quả trùng hợp của `first == second` khi object được cache/intern hoặc tạo từ các nguồn khác nhau.

**(2) So sánh `Boolean` với literal `true` hoặc `false` có thể unbox.**

~~~java
Boolean unknown = null;
// boolean result = (unknown == true); // Nếu chạy: NullPointerException.
~~~

Trong biểu thức `unknown == true`, Java phải unbox `unknown` thành `boolean`. Nếu nó là `null`, sẽ ném `NullPointerException`.

**(3) Kiểm tra nullable an toàn:**

~~~java
Boolean unknown = null;
boolean enabled = Boolean.TRUE.equals(unknown); // false, không NPE.
boolean known = unknown != null;                 // false.
~~~

`Boolean.TRUE.equals(unknown)` trả true **chỉ khi** giá trị là `Boolean.TRUE`; cả `false` và `null` đều cho false. Nếu ứng dụng cần phân biệt ba trạng thái *true / false / unknown*, hãy kiểm tra null riêng thay vì đánh đồng unknown với false.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo file **BooleanComparisonDemo.java**:

~~~java
import java.util.Objects;

public final class BooleanComparisonDemo {
    private static boolean logged(
            StringBuilder order, String name, boolean value) {
        order.append(name);
        return value;
    }

    public static void main(String[] args) {
        boolean ready = true;
        boolean done = false;

        System.out.println("primitiveEqual=" + (ready == done));
        System.out.println("primitiveNotEqual=" + (ready != done));
        System.out.println("negation=" + !done);
        System.out.println("logicalAnd=" + (ready && done));
        System.out.println("logicalOr=" + (ready || done));
        System.out.println("logicalXor=" + (ready ^ done));

        int low = 3;
        int high = 7;
        System.out.println("numericLess=" + (low < high));
        System.out.println("charLess=" + ('A' < 'B'));

        Boolean boxedTrue = Boolean.TRUE;
        Boolean boxedNull = null;
        System.out.println("boxedValue="
                + Boolean.TRUE.equals(boxedTrue));
        System.out.println("nullSafe="
                + Boolean.TRUE.equals(boxedNull));
        System.out.println("bothNull="
                + Objects.equals(boxedNull, null));

        boolean guarded = boxedNull != null && boxedNull;
        System.out.println("nullGuard=" + guarded);

        try {
            boolean unboxed = boxedNull == true;
            System.out.println("unboxed=" + unboxed);
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }

        System.out.println("booleanOrdering="
                + Boolean.compare(false, true));

        String a = new String("Java");
        String b = new String("Java");
        System.out.println("stringValue=" + a.equals(b));
        System.out.println("stringReference=" + (a == b));

        StringBuilder order = new StringBuilder();
        boolean shortAnd = logged(order, "F", false)
                && logged(order, "X", true);
        boolean eagerAnd = logged(order, "A", false)
                & logged(order, "B", true);
        System.out.println("shortAnd=" + shortAnd);
        System.out.println("eagerAnd=" + eagerAnd);
        System.out.println("evaluationOrder=" + order);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 BooleanComparisonDemo.java
java BooleanComparisonDemo
~~~

**Expected stdout chính xác:**

~~~text
primitiveEqual=false
primitiveNotEqual=true
negation=true
logicalAnd=false
logicalOr=true
logicalXor=true
numericLess=true
charLess=true
boxedValue=true
nullSafe=false
bothNull=true
nullGuard=false
unboxNull=NullPointerException
booleanOrdering=-1
stringValue=true
stringReference=false
shortAnd=false
eagerAnd=false
evaluationOrder=FAB
~~~

Giải thích dòng cuối: F cho false nên `&&` bỏ qua X; toán tử boolean `&` vẫn đánh giá cả A và B, do đó dấu vết là `FAB`. Dòng `unboxNull` thể hiện ngoại lệ của so sánh giữa `Boolean` nullable với primitive `true`, không phải giới hạn của `==` trên hai `boolean` nguyên thủy.

## 8. Bài tập tự kiểm tra

**Bài 1.** Cho `boolean a = true, b = false;`. Tính `a == b`, `a != b`, `!a`, `a && b`, `a || b` và `a ^ b`.

**Bài 2.** Giải thích tại sao `true < false`, `false >= true` và `true == 1` không biên dịch trong Java. Có được dùng `'A' < 'B'` không? Vì sao?

**Bài 3.** Khi cần sắp xếp trạng thái false trước true, dùng API nào thay vì `a < b`? Cho ví dụ.

**Bài 4.** Cho `Boolean flag = null;`. Điều gì xảy ra với `flag == true`? So sánh kết quả với `Boolean.TRUE.equals(flag)`.

**Bài 5.** Giải thích sự khác nhau giữa `boolean` và `Boolean`, giữa `Objects.equals(a, b)` và `a == b` khi a, b là các tham chiếu `Boolean`.

### Ghi nhớ

**Hai giá trị `boolean` so sánh được bằng `==` và `!=`, nhưng không dùng được `<`, `<=`, `>`, `>=`.** Boolean không phải số nguyên. Dùng `!`, `&&`, `||` và các phép logic khi làm việc với điều kiện; dùng `Boolean.compare` nếu thật sự cần thứ tự false/true. Với `Boolean` dạng tham chiếu, cẩn thận phép so sánh object và `null` khi unboxing.
