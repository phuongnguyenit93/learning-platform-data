# Thực hành tổng hợp: tái hiện bẫy null, overload, intern và phép nối String với số

## 1. Mục tiêu và cách học

Bài thực hành này yêu cầu **dự đoán kết quả trước khi chạy**, sau đó kiểm tra trên Java 17+ để nhận diện bốn nhóm bẫy thường gặp:

1. **`null`**: tham chiếu rỗng có thể được nối thành chữ `"null"`, gây `NullPointerException` hoặc khiến lời gọi overload không xác định.
2. **Overload**: Java chọn phương thức theo **kiểu của biểu thức lúc biên dịch**, không dựa vào tên lớp thực tế của đối tượng ở runtime để chọn một overload mới.
3. **String pool và `intern()`**: `==` kiểm tra **cùng đối tượng**, còn `equals()` kiểm tra **cùng nội dung**. Literal và biểu thức hằng có cơ chế chia sẻ khác chuỗi được tạo lúc chạy.
4. **Phép nối với số và `char`**: dấu `+` vừa là phép cộng số vừa là nối chuỗi; thứ tự đánh giá và dấu ngoặc ảnh hưởng kết quả.

Mỗi phần gồm đoạn mã, kết quả cần dự đoán, giải thích và cách viết an toàn. Không nên chạy đồng thời những dòng được đánh dấu **lỗi biên dịch** vì chúng được đưa ra để minh họa tình huống sai. Với các ví dụ gây ngoại lệ lúc chạy, đặt lời gọi trong `try/catch` nếu muốn các câu lệnh phía sau tiếp tục thực thi.

## 2. Bẫy null: nối chuỗi không giống gọi phương thức

`String` là **kiểu tham chiếu**. Một biến kiểu `String` có thể chứa tham chiếu `null`, nghĩa là biến đó **không trỏ đến đối tượng String nào**. Điều này khác với chuỗi rỗng `""`.

~~~java
String missing = null;
String empty = "";

System.out.println(missing == null); // true
System.out.println(empty == null);   // false
System.out.println(empty.isEmpty()); // true
~~~

### 2.1. Nối với null tạo chữ "null"

Trong ngữ cảnh nối chuỗi, một tham chiếu `null` được chuyển thành văn bản `"null"`:

~~~java
String value = null;

System.out.println("id=" + value); // id=null
System.out.println(value + "!");   // null!
~~~

Việc này **không chứng minh** biến `value` chứa đối tượng chuỗi có bốn ký tự `n-u-l-l`. Nó vẫn là tham chiếu `null`; phép nối chỉ tạo giá trị chuỗi mới để hiển thị.

Nếu không muốn xuất chữ `null` ra giao diện, xử lý dữ liệu vắng mặt có chủ đích:

~~~java
String label = value == null ? "(chưa có)" : value;
System.out.println("id=" + label); // id=(chưa có)
~~~

Cách này an toàn khi quy ước nghiệp vụ là thay null bằng thông báo cụ thể. Nếu null là dữ liệu lỗi cần từ chối, nên phát hiện và báo lỗi ở nơi phù hợp thay vì im lặng thay thế.

### 2.2. Gọi phương thức trên null gây NullPointerException

~~~java
String value = null;

// value.length();           // NullPointerException khi chạy
// value.concat("!");        // NullPointerException khi chạy
// value.equals("ready");    // NullPointerException khi chạy
~~~

Ngược lại, lời gọi trên một đối tượng có thật có thể so sánh với tham chiếu null:

~~~java
String value = null;

System.out.println("ready".equals(value)); // false
System.out.println(java.util.Objects.equals(value, "ready")); // false
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

Vì thế, với một hằng chuỗi và biến có thể null, `"ready".equals(value)` thường an toàn và dễ đọc. Khi cả hai vế có thể null, `Objects.equals(a, b)` cung cấp so sánh nội dung có xử lý trường hợp null.

Cần phân biệt ý nghĩa: `Objects.equals(null, null)` trả `true` vì **hai tham chiếu đều null**, không có nghĩa tồn tại hai chuỗi có cùng nội dung.

### 2.3. String.valueOf(null) có một bẫy overload

`String.valueOf` có nhiều overload, bao gồm:

~~~java
String.valueOf(Object obj)
String.valueOf(char[] data)
~~~

Hai lời gọi nhìn gần giống nhau nhưng có hành vi khác:

~~~java
System.out.println(String.valueOf((Object) null)); // null

try {
    String.valueOf((char[]) null);
} catch (NullPointerException ex) {
    System.out.println("char[] null => NPE");
}
~~~

Khi truyền `(Object) null`, phương thức `valueOf(Object)` trả chuỗi `"null"`. Khi truyền `(char[]) null`, overload mảng ký tự cần truy cập mảng và ném `NullPointerException`.

Bẫy thú vị hơn:

~~~java
// String.valueOf(null);
~~~

Dòng này **biên dịch được** nhưng Java chọn `valueOf(char[])`, vì `char[]` là kiểu con của `Object` và là overload cụ thể hơn trong các lựa chọn áp dụng. Kết quả là **`NullPointerException` lúc chạy**.

Muốn hành vi chuyển tham chiếu null thành chữ `"null"`, viết rõ:

~~~java
String text = String.valueOf((Object) null);
~~~

Hoặc nếu muốn giá trị thay thế:

~~~java
String text = java.util.Objects.toString(null, "(trống)");
// (trống)
~~~

Thông điệp thực tế: **đừng kết luận từ tên phương thức**. Hãy xem overload nào được chọn theo kiểu đối số.

## 3. Bẫy overload: Java quyết định ở thời điểm biên dịch

Một lớp có thể có nhiều phương thức cùng tên nhưng khác danh sách tham số:

~~~java
static String classify(Object value) {
    return "Object";
}

static String classify(String value) {
    return "String";
}
~~~

Khi gọi:

~~~java
System.out.println(classify("Java")); // String
System.out.println(classify(null));   // String
System.out.println(classify((Object) null)); // Object
~~~

Giải thích:

- Chuỗi `"Java"` có kiểu `String` nên overload nhận `String` khớp cụ thể nhất.
- Literal `null` có thể chuyển sang các kiểu tham chiếu; `String` cụ thể hơn `Object` nên overload `String` được chọn.
- `(Object) null` có **kiểu biểu thức lúc biên dịch là Object**, nên overload nhận `Object` được chọn.

Hàm `classify` trên là phương thức `static` ở ví dụ minh họa. Với các phương thức overload thông thường, Java vẫn phải quyết định **chữ ký phương thức** dựa vào kiểu tại thời điểm biên dịch; *override* (ghi đè phương thức) là cơ chế khác, có thể phân phối phương thức theo loại đối tượng thực lúc chạy.

### 3.1. Hai overload không có kiểu cụ thể hơn: lỗi biên dịch

~~~java
static String inspect(String value) {
    return "String";
}

static String inspect(Integer value) {
    return "Integer";
}

// System.out.println(inspect(null)); // LỖI BIÊN DỊCH: ambiguous
~~~

`String` và `Integer` không phải kiểu con của nhau. Literal `null` áp dụng được cho cả hai, nên compiler không thể chọn overload tốt hơn. Sửa bằng cách nêu rõ ý định:

~~~java
System.out.println(inspect((String) null));  // String
System.out.println(inspect((Integer) null)); // Integer
~~~

Ép kiểu ở đây **chỉ giúp chọn overload**, không tạo đối tượng mới và không biến null thành nội dung chuỗi. Nếu phương thức thật truy cập nội dung của tham số mà không kiểm tra null, vẫn có thể ném ngoại lệ.

### 3.2. Vì sao System.out.println(null) gây mơ hồ?

`PrintStream` có các overload chẳng hạn:

~~~java
println(String x)
println(char[] x)
println(Object x)
~~~

Lời gọi:

~~~java
// System.out.println(null); // LỖI BIÊN DỊCH: ambiguous
~~~

`String` và `char[]` đều cụ thể hơn `Object` nhưng không kiểu nào cụ thể hơn kiểu còn lại. Compiler không chọn được.

Các lời gọi sau có ý nghĩa rõ ràng:

~~~java
System.out.println((String) null); // null
System.out.println((Object) null); // null
~~~

Trong khi đó:

~~~java
// System.out.println((char[]) null); // NullPointerException khi chạy
~~~

Sự khác biệt là overload nhận mảng ký tự định xử lý **phần tử của mảng**, không đơn thuần chuyển đối tượng mảng thành văn bản.

### 3.3. StringBuilder.append(null) cũng có bẫy tương tự

`StringBuilder` có nhiều overload cho `String`, `CharSequence`, `Object` và `char[]`, trong số các kiểu khác.

~~~java
// new StringBuilder().append(null); // LỖI BIÊN DỊCH: ambiguous
~~~

Lời gọi `null` chưa ép kiểu có thể khớp các overload tham chiếu không thể sắp thứ tự “cụ thể nhất”. Hãy nêu rõ kiểu và hành vi mong muốn:

~~~java
System.out.println(new StringBuilder().append((String) null));
// null

System.out.println(new StringBuilder().append((Object) null));
// null
~~~

Nếu dùng overload `append(char[])` với mảng null, sẽ có `NullPointerException` khi chạy. Đây là ví dụ rõ cho nguyên tắc: **lỗi biên dịch do overload mơ hồ và ngoại lệ lúc chạy do truyền null vào phương thức đã chọn là hai loại lỗi khác nhau**.

## 4. String pool, intern() và hai kiểu so sánh

Trong Java:

- `a == b`, nếu `a` và `b` đều là tham chiếu đến đối tượng, kiểm tra **có cùng tham chiếu** hay không.
- `a.equals(b)` với hai chuỗi không null kiểm tra **nội dung chuỗi bằng nhau**.
- `String` là bất biến; hai đối tượng khác nhau hoàn toàn có thể giữ cùng nội dung.

### 4.1. Literal và new String()

~~~java
String a = "java";
String b = "java";
String c = new String("java");

System.out.println(a == b);      // true
System.out.println(a == c);      // false
System.out.println(a.equals(c)); // true
~~~

Các literal `"java"` trong cùng môi trường Java được intern/chia sẻ theo quy tắc của ngôn ngữ, nên `a` và `b` cùng trỏ đến một đối tượng chuỗi pooled. `new String("java")` yêu cầu tạo một đối tượng `String` mới; `c` có cùng nội dung nhưng không cùng tham chiếu với `a`.

Sử dụng `equals()` khi kiểm tra mã trạng thái, username, tên sản phẩm, lựa chọn menu hoặc nội dung nhận từ API/file/database:

~~~java
if ("ACTIVE".equals(status)) {
    // Xử lý khi nội dung status bằng "ACTIVE".
}
~~~

Không dùng `status == "ACTIVE"` để so sánh giá trị nghiệp vụ vì kết quả có thể phụ thuộc việc đối tượng có được chia sẻ hay không.

### 4.2. intern() trả về tham chiếu chuẩn trong string pool

~~~java
String literal = "java";
String created = new String("java");

System.out.println(created == literal);          // false
System.out.println(created.intern() == literal); // true
System.out.println(created.equals(literal));     // true
~~~

`intern()` trả về một tham chiếu chuẩn cho nội dung đó trong *string pool*. Nếu pool đã có một chuỗi bằng nội dung thì `intern()` trả tham chiếu của chuỗi đã có; nếu chưa có, việc quản lý tham chiếu chuẩn diễn ra theo quy tắc của JVM.

Không lạm dụng `intern()` như “mẹo tăng tốc mọi phép so sánh”. Việc đưa nhiều chuỗi riêng biệt vào pool có thể tăng áp lực bộ nhớ/chi phí quản lý; hiệu quả phải xét theo số lượng giá trị lặp lại, vòng đời và yêu cầu ứng dụng. `equals()` vẫn là API đúng để so nội dung, kể cả khi một hoặc cả hai chuỗi đã được intern.

### 4.3. Constant folding và phép nối lúc chạy

Phân biệt biểu thức hằng với biểu thức có biến:

~~~java
String literal = "java";
String folded = "ja" + "va";

String part = "ja";
String runtime = part + "va";

System.out.println(literal == folded);  // true
System.out.println(literal == runtime); // false
System.out.println(literal.equals(runtime)); // true
~~~

`"ja" + "va"` là **biểu thức hằng** nên compiler có thể gộp thành literal `"java"` và dùng tham chiếu interned. `part + "va"` là nối chuỗi tại runtime; kết quả mới có cùng nội dung nhưng không tự động trở thành tham chiếu pooled chỉ vì nội dung trùng một literal.

Nếu `part` là **biến hằng compile-time** đủ điều kiện:

~~~java
final String part = "ja";
String value = part + "va";
System.out.println(value == "java"); // true
~~~

Vì `part` là `final String` được gán bởi một biểu thức hằng, biểu thức nối này cũng là hằng tại compile time. Đừng diễn giải rằng **mọi biến `final` đều tạo biểu thức hằng**: nếu giá trị nhận từ phương thức hoặc input runtime, nó không trở thành compile-time constant chỉ nhờ từ khóa `final`.

**Quy tắc thực hành:** dự đoán `==` để hiểu cơ chế pool; trong mã ứng dụng, dùng `equals()` hoặc `Objects.equals()` để so giá trị.

## 5. Dấu + với số: thứ tự trái sang phải quyết định kết quả

Dấu `+` có hai vai trò:

- Khi cả hai toán hạng phù hợp phép cộng số, Java thực hiện **cộng số** theo quy tắc numeric promotion.
- Khi một toán hạng là `String`, Java thực hiện **nối chuỗi**, chuyển toán hạng còn lại thành biểu diễn văn bản.

Các toán tử cộng/nối cùng độ ưu tiên được liên kết **từ trái sang phải**. Dấu ngoặc làm thay đổi nhóm biểu thức:

~~~java
System.out.println(1 + 2 + "3");   // 33
System.out.println("1" + 2 + 3);   // 123
System.out.println("1" + (2 + 3)); // 15
System.out.println((1 + 2) + "3"); // 33
~~~

Giải thích từng bước:

1. `1 + 2 + "3"`: `1 + 2` là cộng số tạo `3`; sau đó `3 + "3"` tạo chuỗi `"33"`.
2. `"1" + 2 + 3`: bắt đầu bằng String nên `"1" + 2` thành `"12"`; tiếp tục `"12" + 3` thành `"123"`.
3. `"1" + (2 + 3)`: biểu thức trong ngoặc cho `5` trước, rồi nối thành `"15"`.
4. `(1 + 2) + "3"` cho cùng nội dung `"33"` như ví dụ đầu vì hai số đã được cộng trước.

Với một biến số:

~~~java
int price = 10;
int fee = 5;

System.out.println("Total: " + price + fee);   // Total: 105
System.out.println("Total: " + (price + fee)); // Total: 15
~~~

Dấu ngoặc làm rõ ý định phép cộng. Đây là lỗi tính đúng của chương trình, không phải vấn đề hiệu năng.

### 5.1. char cộng số: thường ra mã số, không ra ký tự kế tiếp

`char` là một kiểu số nguyên 16 bit không dấu. Trong phép cộng số với `int`, `char` được nâng kiểu để tính toán:

~~~java
System.out.println('A' + 1);     // 66
System.out.println("A" + 1);     // A1
System.out.println("char=" + 'A' + 1); // char=A1
~~~

`'A' + 1` không in chữ `B`: biểu thức có kiểu `int` và giá trị `65 + 1 = 66`. Nếu thật sự muốn ký tự tiếp theo trong phạm vi phù hợp:

~~~java
char next = (char) ('A' + 1);
System.out.println(next); // B
~~~

Cách này chỉ là phép toán trên giá trị UTF-16 và **không phải** thuật toán tăng “ký tự Unicode hiển thị” nói chung.

### 5.2. Phép nối với null và số cùng lúc

~~~java
String missing = null;

System.out.println("x=" + missing + 1);  // x=null1
System.out.println("x=" + (1 + 2));      // x=3
System.out.println((Object) null + "3"); // null3
~~~

Chọn rõ dấu ngoặc và cách thay thế null. Ví dụ `"x=" + (missing == null ? 0 : Integer.parseInt(missing)) + 1` vẫn sẽ nối `1` sau khi bắt đầu bằng String; để tính tổng cần bao toàn bộ phép tính: `"x=" + ((missing == null ? 0 : Integer.parseInt(missing)) + 1)`.

## 6. StringBuilder.append() cũng phân biệt kiểu dữ liệu

`StringBuilder` có nhiều overload; kết quả có thể khác nhau theo biểu thức truyền vào:

~~~java
StringBuilder a = new StringBuilder();
a.append('A').append(1);
System.out.println(a); // A1

StringBuilder b = new StringBuilder();
b.append('A' + 1);
System.out.println(b); // 66
~~~

Ở trường hợp `a`, `append(char)` in chữ `A` và `append(int)` nối ký hiệu số `1`. Ở trường hợp `b`, phép cộng `'A' + 1` thực hiện **trước khi gọi `append`**, tạo số nguyên `66`, nên overload `append(int)` hiển thị `66`.

Dùng hai lời gọi riêng khi muốn nối ký tự và số, dùng phép cộng rõ ràng khi muốn tính toán:

~~~java
String message = new StringBuilder()
        .append("Result: ")
        .append(1 + 2)
        .toString();
// Result: 3
~~~

Với vài phần cố định, `"Result: " + (1 + 2)` còn ngắn hơn. Không thay `+` bằng `StringBuilder` chỉ để tránh bẫy thứ tự phép toán: cả hai đều cần thể hiện đúng ý định.

## 7. Chương trình Java 17+ chạy hoàn chỉnh

Tạo tệp **`StringPitfallsDemo.java`**:

~~~java
import java.util.Objects;

public class StringPitfallsDemo {
    static String classify(Object value) {
        return "Object";
    }

    static String classify(String value) {
        return "String";
    }

    static String inspect(String value) {
        return "String";
    }

    static String inspect(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        String missing = null;
        System.out.println("plus null: " + ("id=" + missing));
        System.out.println("safe equals: " + "ok".equals(missing));
        System.out.println("both null: " + Objects.equals(null, null));

        System.out.println(
                "valueOf(Object): " + String.valueOf((Object) null));

        try {
            String.valueOf((char[]) null);
        } catch (NullPointerException ex) {
            System.out.println("valueOf(char[]): NPE");
        }

        System.out.println("overload(null): " + classify(null));
        System.out.println(
                "overload((Object)null): " + classify((Object) null));
        System.out.println(
                "inspect((String)null): " + inspect((String) null));

        // Không bỏ comment: đây là lỗi overload mơ hồ khi biên dịch.
        // inspect(null);
        // System.out.println(null);
        // new StringBuilder().append(null);

        String literal = "java";
        String created = new String("java");
        System.out.println("literal == new: " + (literal == created));
        System.out.println(
                "literal equals new: " + literal.equals(created));
        System.out.println(
                "intern identity: " + (literal == created.intern()));

        String folded = "ja" + "va";
        String part = "ja";
        String runtime = part + "va";
        System.out.println("folded identity: " + (literal == folded));
        System.out.println("runtime identity: " + (literal == runtime));
        System.out.println(
                "runtime equality: " + literal.equals(runtime));

        System.out.println("numeric first: " + (1 + 2 + "3"));
        System.out.println("string first: " + ("1" + 2 + 3));
        System.out.println("grouped: " + ("1" + (2 + 3)));
        System.out.println("char plus int: " + ('A' + 1));
        System.out.println("char then string: " + ("A" + 1));

        StringBuilder builder = new StringBuilder();
        builder.append('A').append(1);
        System.out.println("builder: " + builder);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringPitfallsDemo.java
java StringPitfallsDemo
~~~

Đầu ra:

~~~text
plus null: id=null
safe equals: false
both null: true
valueOf(Object): null
valueOf(char[]): NPE
overload(null): String
overload((Object)null): Object
inspect((String)null): String
literal == new: false
literal equals new: true
intern identity: true
folded identity: true
runtime identity: false
runtime equality: true
numeric first: 33
string first: 123
grouped: 15
char plus int: 66
char then string: A1
builder: A1
~~~

### Vì sao kết quả như vậy?

- `missing` là tham chiếu null, được nối thành chữ `null`; nhưng `"ok".equals(missing)` vẫn là `false` và không gọi phương thức trên null.
- `Objects.equals(null, null)` so sánh hai giá trị null nên cho `true`.
- `String.valueOf((Object) null)` tạo chuỗi `"null"`, trong khi `String.valueOf((char[]) null)` ném `NullPointerException` vì overload mảng.
- `classify(null)` chọn overload `String` là overload cụ thể hơn `Object`; ép kiểu `(Object) null` chuyển lựa chọn sang overload `Object`.
- `inspect(null)` được để ở dạng comment vì `String` và `Integer` không có quan hệ kiểu cụ thể hơn; thêm cast chọn overload được mong muốn.
- Literal, biểu thức nối hằng và `intern()` liên hệ đến cùng tham chiếu pool; đối tượng `new String(...)` và kết quả nối runtime là các đối tượng khác trong ví dụ này, dù `equals()` đều so nội dung thành `true`.
- Các biểu thức `+` cho `33`, `123` và `15` tương ứng với nhóm phép cộng/nối.
- `'A' + 1` cho số 66; `"A" + 1` cho chuỗi `A1`; `append('A').append(1)` cũng cho `A1`.

## 8. Bài tập dự đoán và tự kiểm tra

Hãy ghi dự đoán **giá trị**, **kiểu kết quả** và liệu lỗi xảy ra **lúc biên dịch** hay **lúc chạy** trước khi xem đáp án.

### Bài 1: null và equals

~~~java
String x = null;
System.out.println("x=" + x);
System.out.println("go".equals(x));
System.out.println(x == null);
~~~

**Đáp án:** lần lượt `x=null`, `false`, `true`. `"go".equals(x)` gọi trên literal không null, còn phép `== null` kiểm tra tham chiếu.

### Bài 2: null và overload

~~~java
// A
String.valueOf((Object) null);

// B
String.valueOf((char[]) null);

// C
String.valueOf(null);
~~~

**Đáp án:** A trả `"null"`; B ném `NullPointerException`; C **biên dịch được nhưng cũng ném `NullPointerException`** vì chọn overload nhận `char[]`. Đây là trường hợp dễ nhầm giữa lời gọi `valueOf(Object)` và `valueOf(char[])`.

### Bài 3: overload mơ hồ

~~~java
static void f(String x) {}
static void f(Integer x) {}

// f(null);
~~~

**Đáp án:** `f(null)` không biên dịch vì cả hai overload áp dụng và không overload nào cụ thể hơn. `f((String) null)` và `f((Integer) null)` hợp lệ về mặt lựa chọn overload.

### Bài 4: so sánh String

~~~java
String x = "ab";
String y = "a" + "b";
String p = "a";
String z = p + "b";

System.out.println(x == y);
System.out.println(x == z);
System.out.println(x.equals(z));
~~~

**Đáp án:** `true`, `false`, `true`. `y` là biểu thức hằng; `z` được tạo bằng nối lúc chạy.

### Bài 5: cộng số hay nối chuỗi?

~~~java
System.out.println(10 + 5 + " USD");
System.out.println("USD " + 10 + 5);
System.out.println("USD " + (10 + 5));
~~~

**Đáp án:** `15 USD`, `USD 105`, `USD 15`. Dấu ngoặc quyết định hai số được cộng trước hay lần lượt chuyển thành chuỗi.

### Bài 6: char và StringBuilder

~~~java
System.out.println('0' + 1);

StringBuilder sb = new StringBuilder();
sb.append('0').append(1);
System.out.println(sb);
~~~

**Đáp án:** `49` và `01`. `'0'` có mã số 48; `'0' + 1` là cộng số. Hai lần `append` lần lượt thêm ký tự và chữ số.

### Bài 7: hai kiểu lỗi khác nhau

~~~java
// System.out.println(null);     // A
// System.out.println((char[]) null); // B
~~~

**Đáp án:** A không biên dịch vì mơ hồ giữa overload `String` và `char[]`. B chọn rõ overload `char[]` nhưng ném `NullPointerException` lúc chạy. Ép kiểu xử lý **lựa chọn overload**, không đảm bảo truyền null là hợp lệ.

### Bài 8: final và biểu thức hằng

~~~java
final String a = "ja";
String x = a + "va";
String y = "java";
System.out.println(x == y);
~~~

**Đáp án:** `true`. `a` là biến hằng compile-time của kiểu `String`, được gán bằng biểu thức hằng; nối với `"va"` cũng là biểu thức hằng. Không áp dụng quy tắc này cho mọi biến `final` mà giá trị chỉ được biết lúc chạy.

## 9. Phân biệt compile-time error, runtime error và lỗi logic

| Tình huống | Kết quả | Nguyên nhân |
|---|---|---|
| `String.valueOf(null)` | `NullPointerException` khi chạy | Chọn overload `char[]` cụ thể hơn `Object` |
| `String.valueOf((Object) null)` | Chuỗi `"null"` | Chọn overload `Object` |
| `System.out.println(null)` | Lỗi biên dịch | Overload `String` và `char[]` mơ hồ |
| `new StringBuilder().append(null)` | Lỗi biên dịch | Các overload kiểu tham chiếu không có lựa chọn cụ thể duy nhất |
| `missing.length()` khi `missing == null` | `NullPointerException` | Gọi phương thức trên tham chiếu null |
| `new String("java") == "java"` | `false` | Hai đối tượng khác nhau |
| `new String("java").equals("java")` | `true` | Nội dung bằng nhau |
| `"Total: " + 10 + 5` | `"Total: 105"` | Nối chuỗi từ trái sang phải |
| `"Total: " + (10 + 5)` | `"Total: 15"` | Cộng số trong ngoặc trước |
| `'A' + 1` | `int` 66 | Phép cộng số và numeric promotion |

Điều quan trọng nhất khi gỡ lỗi là phân loại đúng:

- **Lỗi biên dịch:** JVM chưa chạy chương trình; thay đổi cast/chữ ký để compiler biết overload nào được gọi.
- **Ngoại lệ lúc chạy:** code đã biên dịch nhưng một tham chiếu null bị sử dụng theo cách không hợp lệ; kiểm tra dữ liệu và contract.
- **Sai logic:** code chạy bình thường nhưng kết quả không đúng yêu cầu, chẳng hạn dùng `==` so nội dung hay quên ngoặc khi cộng số.

Đừng dùng `try/catch` để “sửa” một lỗi overload mơ hồ: lỗi đó xảy ra trước khi chương trình có thể chạy.

## 10. Cách viết mã an toàn trong dự án thực tế

### 10.1. So sánh nội dung bằng equals

~~~java
boolean accepted = "OK".equals(status);
boolean same = java.util.Objects.equals(firstName, secondName);
~~~

Cách viết giảm rủi ro `NullPointerException` do gọi `equals` trên tham chiếu có thể null. Để kiểm tra cùng tham chiếu cho mục đích nhận diện đối tượng, `==` vẫn phù hợp; vấn đề là không dùng nhầm nó như phép so sánh nội dung chuỗi.

### 10.2. Giải quyết null theo yêu cầu nghiệp vụ

~~~java
String displayName = java.util.Objects.toString(userName, "(ẩn danh)");
~~~

Nếu null là dữ liệu thiếu cần thông báo, truyền giá trị thay thế có ý nghĩa. Nếu đầu vào bắt buộc không null, xác thực ở ranh giới nhận dữ liệu, ví dụ dùng `Objects.requireNonNull` với thông báo rõ ràng.

### 10.3. Làm rõ overload bằng kiểu và tên

Khi overload có thể dẫn đến mơ hồ với literal null, tốt hơn nên thiết kế API với tên phương thức khác nhau cho hai hành vi khác nhau nếu điều đó giúp mã dễ hiểu:

~~~java
static String fromText(String text) {
    return text == null ? "" : text;
}

static String fromNumber(Integer number) {
    return number == null ? "" : number.toString();
}
~~~

Nếu vẫn sử dụng overload, truyền biến có kiểu tĩnh rõ ràng hoặc cast phù hợp; không dùng cast tùy tiện chỉ để làm mất cảnh báo biên dịch.

### 10.4. Viết ngoặc rõ cho phép tính

~~~java
int quantity = 2;
int unitPrice = 50;

String total = "Total: " + (quantity * unitPrice);
~~~

Dù `*` có độ ưu tiên cao hơn `+`, dấu ngoặc vẫn giúp người đọc thấy phần tính toán riêng với phần nối chuỗi. Với phép cộng hỗn hợp, dấu ngoặc còn quyết định đúng/sai:

~~~java
String totalWithFee = "Total: " + (quantity * unitPrice + 10);
~~~

### 10.5. Hiểu intern mà không phụ thuộc intern

Không cần intern thủ công mọi chuỗi chỉ để so sánh:

~~~java
String source = new String("READY");
boolean sameContent = "READY".equals(source); // true
~~~

`equals` giữ đúng ngữ nghĩa kể cả khi chuỗi đến từ file, HTTP, database, đối tượng mới hoặc string pool. Nếu có yêu cầu tối ưu bộ nhớ cho nhiều chuỗi trùng lặp, cần đo và thiết kế riêng; không biến giả định về tham chiếu pooled thành logic nghiệp vụ.

## 11. Checklist gỡ lỗi khi kết quả gây bất ngờ

Khi gặp một biểu thức String trong Java:

1. **Xác định kiểu của từng biểu thức ở compile time.** Với null, hỏi overload nào hợp lệ và overload nào cụ thể nhất.
2. **Xác định null là giá trị dữ liệu hay tham chiếu không có đối tượng.** Phép nối `+`, `String.valueOf` và lời gọi phương thức có thể xử lý khác nhau.
3. **Hỏi đang so sánh tham chiếu hay nội dung.** `==` là nhận diện tham chiếu, `equals` là so sánh nội dung.
4. **Xác định chuỗi được tạo khi nào.** Literal/biểu thức hằng và nối runtime khác nhau về quy tắc intern.
5. **Thêm ngoặc để nhìn rõ phép cộng.** Một toán hạng String làm thay đổi ý nghĩa `+` thành nối chuỗi.
6. **Đọc compiler error trước khi sửa.** Ambiguous overload là lỗi chọn chữ ký, khác hoàn toàn NullPointerException.
7. **Chạy một chương trình tối thiểu có đầu ra xác định.** Kiểm tra cả giá trị, kiểu và trường hợp lỗi; không suy luận chỉ từ tên API.
8. **Viết test bảo vệ hành vi.** Các giá trị null, chuỗi rỗng, literal/new String, compile-time constant, số và char là những tình huống nên có ví dụ kiểm thử tương ứng.

## 12. Ghi nhớ

Bốn nhóm bẫy có chung nguyên nhân: **cùng một cách viết gần giống nhau nhưng Java áp dụng quy tắc khác theo kiểu, ngữ cảnh và thời điểm tạo giá trị**.

- `null` trong phép nối có thể thành chữ `"null"`; gọi phương thức trên null có thể ném `NullPointerException`.
- Overload được xác định theo **kiểu đối số lúc biên dịch**; cast làm rõ lựa chọn nhưng không tự sửa dữ liệu null.
- `intern()` và constant folding liên quan đến **đối tượng được chia sẻ**; để kiểm tra nội dung String, dùng `equals()`.
- `+` vừa cộng số vừa nối chuỗi; thứ tự trái sang phải và dấu ngoặc quyết định kết quả.

Cách học hiệu quả nhất là tự đoán **biên dịch được không, nếu chạy sẽ in gì và vì sao**, rồi đối chiếu với các ví dụ Java 17+ trước khi áp dụng quy tắc vào chương trình lớn.
