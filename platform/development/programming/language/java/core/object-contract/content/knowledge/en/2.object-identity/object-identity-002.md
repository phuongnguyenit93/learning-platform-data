# Toán tử `==` và `!=` trên tham chiếu trong Java

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa **danh tính đối tượng (identity)** và **bằng nhau về giá trị hoặc trạng thái (logical equality)**.
- Dự đoán kết quả của `==` và `!=` khi hai biến tham chiếu trỏ đến cùng đối tượng, hai đối tượng khác nhau hoặc `null`.
- Chọn `==`, `!=`, `equals()` hay `Objects.equals()` đúng tình huống.
- Nhận ra các trường hợp dễ nhầm với `String`, kiểu bao (wrapper), mảng, `enum` và `record`.

## 1. Tham chiếu là gì và `==` thực sự so sánh điều gì?

Một biến kiểu tham chiếu có thể giữ tham chiếu đến một đối tượng hoặc giá trị `null`. Hai biến có thể cùng trỏ đến **một đối tượng**, dù chúng có hai tên khác nhau. Ngược lại, hai đối tượng có thể có dữ liệu hoàn toàn giống nhau nhưng vẫn là **hai đối tượng riêng biệt**.

Với hai toán hạng kiểu tham chiếu tương thích:

- `a == b` trả về `true` nếu cả hai cùng tham chiếu đến **chính một đối tượng**, hoặc **cả hai đều là `null`**; ngược lại trả về `false`.
- `a != b` là kết quả phủ định của `a == b`: trả về `true` khi hai tham chiếu không đồng nhất.
- Kết quả là kiểu nguyên thủy `boolean`. Không có việc gọi `equals()` ngầm khi dùng `==` hoặc `!=` trên hai tham chiếu.
- Gán một biến tham chiếu sang biến khác **sao chép giá trị tham chiếu**, không sao chép đối tượng.

Ví dụ:

```java
Object original = new Object();
Object alias = original;       // Cùng đối tượng
Object another = new Object(); // Đối tượng khác

System.out.println(original == alias);   // true
System.out.println(original == another); // false
System.out.println(original != another); // true
```

Dù hai lần tạo `new Object()` có thể tạo đối tượng cùng kiểu và không có dữ liệu riêng để phân biệt, chúng vẫn mang danh tính khác nhau. Sự so sánh này không dựa vào nội dung trường, địa chỉ bộ nhớ hiển thị, tên biến hay kết quả `hashCode()`.

### `==` với kiểu nguyên thủy là phép so sánh khác

Khi cả hai toán hạng là giá trị nguyên thủy phù hợp, chẳng hạn `int` hoặc `boolean`, `==` so sánh **giá trị**. Vì thế, luôn xác định kiểu của hai toán hạng trước khi suy luận:

```java
int x = 42;
int y = 42;
System.out.println(x == y); // true: so sánh giá trị int

Integer boxedX = 42;
Integer boxedY = 42;
System.out.println(boxedX == boxedY); // true: hai tham chiếu tới Integer được cache
```

Hai dòng cùng in `true` nhưng do **hai cơ chế khác nhau**. Phần về wrapper bên dưới sẽ chỉ rõ giới hạn của việc cache.

## 2. Ví dụ hoàn chỉnh, biên dịch và chạy bằng Java 17+

Lưu nội dung sau vào tệp `IdentityOperatorsDemo.java`. Đây là một chương trình độc lập, trong đó `Pair` là một `record` lồng bên trong lớp.

```java
import java.util.Arrays;

public class IdentityOperatorsDemo {
    record Pair(int left, int right) {}

    public static void main(String[] args) {
        Object first = new Object();
        Object alias = first;
        Object second = new Object();

        System.out.println("same object: " + (first == alias));
        System.out.println("different objects: " + (first != second));

        Object missing = null;
        System.out.println("missing == null: " + (missing == null));
        System.out.println("missing != first: " + (missing != first));

        String s1 = "java";
        String s2 = "java";
        String s3 = new String("java"); // Chỉ dùng để minh họa danh tính
        System.out.println("literal == literal: " + (s1 == s2));
        System.out.println("literal == new: " + (s1 == s3));
        System.out.println("literal.equals(new): " + s1.equals(s3));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        int[] arrayAlias = arrayA;
        System.out.println("array == alias: " + (arrayA == arrayAlias));
        System.out.println("array == array: " + (arrayA == arrayB));
        System.out.println("Arrays.equals: " + Arrays.equals(arrayA, arrayB));

        Pair p1 = new Pair(1, 2);
        Pair p2 = new Pair(1, 2);
        System.out.println("record ==: " + (p1 == p2));
        System.out.println("record.equals: " + p1.equals(p2));
    }
}
```

Trong terminal (đã cài JDK 17 trở lên):

```bash
javac IdentityOperatorsDemo.java
java IdentityOperatorsDemo
```

Kết quả chuẩn:

```text
same object: true
different objects: true
missing == null: true
missing != first: true
literal == literal: true
literal == new: false
literal.equals(new): true
array == alias: true
array == array: false
Arrays.equals: true
record ==: false
record.equals: true
```

Đối chiếu từng nhóm: `alias` và `arrayAlias` dùng lại đối tượng đã có; mỗi lệnh `new` tạo đối tượng mới; `equals()` của `String` so sánh chuỗi ký tự; `Arrays.equals` so sánh phần tử của hai mảng `int[]`; còn `record` tự cung cấp phép `equals()` dựa trên các thành phần của nó. Trong trường hợp `s1`/`s2`, hai chuỗi literal cùng nội dung được Java dùng chung qua cơ chế intern.

## 3. So sánh với `null` và kiểm tra trước khi truy cập đối tượng

`null` biểu thị không có đối tượng được tham chiếu. Kiểm tra `a == null` hoặc `a != null` hợp lệ và **không tự gây `NullPointerException`**; chúng chỉ so sánh tham chiếu. `null == null` là `true`; `null != null` là `false`.

```java
String name = null;

if (name == null) {
    System.out.println("Chưa có tên");
}
if (name != null && !name.isBlank()) {
    System.out.println(name);
}
```

Trong điều kiện thứ hai, `&&` đánh giá từ trái sang phải và ngắn mạch: nếu `name != null` là `false` thì `name.isBlank()` không được gọi. Ngược lại, gọi `name.equals("A")` khi `name` là `null` sẽ ném `NullPointerException`.

Khi muốn so sánh **nội dung** mà một hoặc cả hai giá trị có thể `null`, dùng `Objects.equals(a, b)` (cần `import java.util.Objects;`). Hàm trả về `true` nếu hai tham chiếu cùng một đối tượng, cả hai `null`, hoặc nếu `a` khác `null` và `a.equals(b)` là `true`.

```java
import java.util.Objects;

// Phần thân một phương thức:
String a = null;
String b = "Java";
boolean sameContent = Objects.equals(a, b); // false, an toàn với null
boolean bothAbsent = Objects.equals(null, null); // true
```

Đây là **đoạn mã minh họa đặt trong một phương thức**, không phải tệp Java độc lập vì có các lệnh bên ngoài khai báo lớp và một lệnh `import`.

## 4. Vì sao `String` là bẫy thường gặp?

`String` là kiểu tham chiếu, dù cú pháp literal như `"Java"` trông giống giá trị. Java dùng cơ chế **string interning** để các literal cùng nội dung dùng chung một đối tượng `String`. Vì vậy:

```java
String a = "Java";
String b = "Java";
String c = new String("Java");

System.out.println(a == b);      // true: cùng đối tượng literal được intern
System.out.println(a == c);      // false: new tạo đối tượng khác
System.out.println(a.equals(c));  // true: cùng nội dung ký tự
```

Mục tiêu ở đây là chứng minh `==` phụ thuộc **danh tính**, không chứng minh nội dung. Không viết logic nghiệp vụ phụ thuộc vào việc hai chuỗi bất kỳ có dùng chung đối tượng hay không. Dùng `a.equals(b)` khi `a` chắc chắn khác `null`; dùng `Objects.equals(a, b)` khi có thể `null`. `equalsIgnoreCase` là lựa chọn riêng khi cần so sánh chuỗi không phân biệt hoa/thường, với quy tắc so sánh riêng của `String`.

Lệnh `new String("Java")` chỉ có ý nghĩa giảng dạy ở đây; trong mã ứng dụng, thường không cần tạo bản sao từ một literal. Nếu chủ động gọi `intern()`, bạn đang nhận chuỗi đại diện canonical của nội dung đó, nhưng không nên dùng thao tác này làm cách thay thế tổng quát cho so sánh nội dung.

## 5. Wrapper và autoboxing: cần xét kiểu của từng toán hạng

`Integer`, `Long`, `Boolean` và các wrapper khác là lớp, nên nếu **cả hai toán hạng đều là tham chiếu wrapper**, `==` xét danh tính. Với `Integer`, Java bảo đảm việc boxing/`Integer.valueOf` dùng chung đối tượng cho các giá trị từ **-128 đến 127**. Hành vi cache cho các giá trị lớn hơn có thể khác giữa môi trường triển khai và cấu hình, nên không được dựa vào `==` để so sánh giá trị số của wrapper.

```java
Integer a = 127;
Integer b = 127;
Integer c = 1_000;
Integer d = 1_000;

System.out.println(a == b);      // true: bảo đảm cho giá trị 127
System.out.println(c.equals(d));  // true: cùng giá trị 1000
// Không suy luận c == d luôn là false trên mọi môi trường.
```

Nếu một toán hạng là `Integer` và toán hạng kia là `int`, phép so sánh số có thể **unbox** wrapper về `int`, sau đó so sánh giá trị:

```java
Integer boxed = 5;
int primitive = 5;

System.out.println(boxed == primitive); // true: unboxing rồi so sánh int
```

Nhưng unboxing một tham chiếu wrapper `null` gây `NullPointerException`:

```java
Integer boxed = null;
int primitive = 5;
// boolean result = boxed == primitive; // Ném NullPointerException khi chạy
```

Do đó đừng áp dụng một quy tắc máy móc kiểu “hễ có wrapper thì `==` luôn so sánh tham chiếu”; **kiểu thực tế của hai toán hạng** quyết định liệu có chuyển đổi/unboxing hay không. Khi muốn so sánh hai wrapper theo giá trị và chấp nhận `null`, `Objects.equals(a, b)` thường rõ ràng hơn.

## 6. Mảng, `record` và `enum`

**Mảng:** Hai mảng có cùng phần tử vẫn là hai đối tượng khác nhau. `arr1 == arr2` chỉ xác định liệu chúng có cùng là một mảng hay không. Với mảng một chiều chứa kiểu nguyên thủy, dùng `Arrays.equals(arr1, arr2)` để so sánh phần tử; với mảng đa chiều, cân nhắc `Arrays.deepEquals`. Với mảng đối tượng, `Arrays.equals` so sánh các phần tử theo `equals()` với xử lý `null`, và không tự so sánh sâu cấu trúc lồng nhau.

**`record`:** Hai bản ghi cùng giá trị thành phần nhưng tạo bởi hai lệnh `new` là hai đối tượng riêng. `==` trả về `false`; `equals()` do `record` sinh ra kiểm tra các thành phần theo hợp đồng của record. Ví dụ `new Pair(1, 2).equals(new Pair(1, 2))` là `true` với khai báo `Pair` ở phần 2.

**`enum`:** Mỗi enum constant là một thực thể duy nhất của kiểu enum đó; do vậy `==` rất phù hợp khi so sánh các constant và không cần gọi `equals()`. Ví dụ sau dùng được trong thân một phương thức:

```java
enum Status { NEW, DONE }

// Trong phương thức:
Status current = Status.NEW;
boolean isNew = current == Status.NEW; // true
boolean isDone = current != Status.DONE; // true
```

Đoạn cuối minh họa cú pháp và ý nghĩa; để chạy riêng, hãy đặt khai báo `enum` trong phạm vi cho phép và các lệnh biến vào phương thức.

## 7. Kiểu tham chiếu phải tương thích khi viết phép so sánh

Java kiểm tra tính hợp lệ của phép `==`/`!=` ngay lúc biên dịch. Hai toán hạng tham chiếu phải thỏa các quy tắc kiểu của phép so sánh bằng; không phải hai kiểu tham chiếu bất kỳ đều được đặt cạnh `==`. Ví dụ:

```java
String text = "1";
Integer number = 1;
// boolean wrong = text == number; // Lỗi biên dịch: kiểu không thể so sánh
Object o = text;
boolean allowed = o == number;    // Hợp lệ về kiểu, trả về false ở đây
```

Trường hợp `o == number` hợp lệ vì biểu thức có thể được xem là các tham chiếu đối tượng tương thích cho phép so sánh; không có nghĩa hai giá trị được chuyển thành chuỗi hay số để so sánh nội dung. Nếu cần so sánh dữ liệu khác kiểu, hãy xác định quy tắc chuyển đổi rõ ràng trước khi so sánh **giá trị**.

## 8. Chọn phép so sánh theo câu hỏi cần trả lời

| Câu hỏi | Cách viết phù hợp | Ý nghĩa |
| --- | --- | --- |
| Hai tham chiếu có trỏ cùng đối tượng? | `a == b` | Identity; cả hai `null` cũng cho `true` |
| Hai tham chiếu có trỏ khác đối tượng? | `a != b` | Phủ định identity |
| Biến có vắng mặt? | `a == null` | Kiểm tra `null` an toàn |
| Biến có đối tượng? | `a != null` | Kiểm tra trước khi truy cập |
| Hai `String` có cùng nội dung? | `a.equals(b)` | Dùng khi `a` không `null` |
| Hai giá trị tham chiếu có bằng nhau theo `equals`, kể cả `null`? | `Objects.equals(a, b)` | So sánh logic an toàn với `null` |
| Hai mảng có phần tử tương ứng bằng nhau? | `Arrays.equals(a, b)` | So sánh nội dung mảng một chiều |
| Hai enum constant có giống nhau? | `status == Status.NEW` | So sánh identity tự nhiên cho `enum` |

Lưu ý: `equals()` là **phương thức**, có thể được lớp ghi đè để định nghĩa bằng nhau theo trạng thái; `==` là **toán tử của ngôn ngữ** và không được overload. Nếu lớp không ghi đè `Object.equals()`, phương thức mặc định dùng identity tương đương với `==`. Khi ghi đè `equals()`, cần tuân thủ hợp đồng bằng nhau và ghi đè `hashCode()` nhất quán; đó là chủ đề sâu hơn của hợp đồng đối tượng.

## 9. Lỗi thường gặp và cách tránh

1. **Dùng `==` để so sánh đầu vào `String`.** Các chuỗi trông giống nhau có thể là đối tượng khác nhau. Chọn `equals()` hoặc `Objects.equals()` nếu cần so nội dung.
2. **Cho rằng hai đối tượng cùng trường thì `==` là `true`.** Hai lần `new` tạo hai danh tính riêng; nội dung thuộc phạm vi `equals()` do kiểu quy định.
3. **Dùng `==` trên hai `Integer` chỉ vì một vài test cho kết quả đúng.** Cache có thể che lỗi. Dùng so sánh giá trị.
4. **Quên `null` khi gọi `equals()` hoặc unboxing.** Kiểm tra `null`, dùng `Objects.equals`, hoặc thiết kế dữ liệu không nhận `null` khi hợp lý.
5. **Nhầm `==` với `Arrays.equals`.** `==` hỏi có cùng đối tượng mảng, không hỏi các phần tử có trùng.
6. **Suy luận identity qua `hashCode()`, `System.identityHashCode()` hoặc địa chỉ hiển thị.** Giá trị hash không bảo đảm duy nhất cho mỗi đối tượng. Muốn biết hai tham chiếu có cùng đối tượng, dùng `==`.
7. **Quên quy tắc tương thích kiểu.** Phép so sánh `==` giữa hai tham chiếu có kiểu không thể so sánh có thể không biên dịch, dù ta nghĩ kết quả hiển nhiên là `false`.

## 10. Tự kiểm tra

Hãy dự đoán các biểu thức sau trước khi xem giải thích:

```java
Object a = new Object();
Object b = a;
Object c = new Object();

String x = new String("ok");
String y = new String("ok");

Integer n = null;

boolean q1 = a == b;
boolean q2 = a != c;
boolean q3 = x == y;
boolean q4 = x.equals(y);
boolean q5 = n == null;
```

**Đáp án:** `q1 = true` vì `a` và `b` là hai bí danh của một đối tượng; `q2 = true` vì `c` là đối tượng mới; `q3 = false` vì có hai đối tượng `String` được tạo bằng `new`; `q4 = true` do nội dung chuỗi giống nhau; `q5 = true` vì `n` là tham chiếu `null` và ở đây không có unboxing.

**Ghi nhớ:** với hai toán hạng tham chiếu, `==`/`!=` trả lời câu hỏi **“có cùng đối tượng hay không?”**. Khi cần so sánh dữ liệu, phải dựa vào hợp đồng `equals()` của kiểu hoặc API so sánh nội dung thích hợp.