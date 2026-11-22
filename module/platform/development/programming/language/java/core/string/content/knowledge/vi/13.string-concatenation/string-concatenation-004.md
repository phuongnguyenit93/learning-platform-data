# String.concat và khác biệt khi đối số là null

Trong Java, có nhiều cách nối chuỗi, nhưng **String.concat(String str)** và toán tử **+** không xử lý **null** giống nhau. Đây là điểm dễ gây lỗi khi nối tên, mã, thông báo hoặc dữ liệu từ API mà một thành phần có thể chưa được cung cấp.

- **"Java".concat(" 17")** trả về String có nội dung **"Java 17"**.
- **"Java".concat(null)** ném **NullPointerException**.
- **"Java" + null** tạo String có nội dung **"Javanull"**: toán tử nối chuỗi chuyển tham chiếu null thành chữ **"null"**.
- Nếu **biến nhận lời gọi concat() là null**, ví dụ **prefix.concat(" 17")**, cũng ném **NullPointerException**.
- **String.concat() không sửa String gốc**: String bất biến, kết quả phải được sử dụng hoặc gán cho một biến.

Sự khác nhau không chỉ là vấn đề cú pháp; nó còn quyết định cách ứng dụng diễn đạt dữ liệu vắng mặt. Chữ "null" xuất hiện trong kết quả nối chuỗi thường là **dấu hiệu dữ liệu chưa được xử lý theo chính sách nghiệp vụ**, không mặc nhiên là nội dung người dùng muốn nhìn thấy.

## 1. Hiểu đúng chữ ký của String.concat()

Phương thức của lớp String có dạng:

~~~java
public String concat(String str)
~~~

Đây là **chữ ký API để giải thích**, không phải một phương thức bạn cần tự định nghĩa. **str** phải là tham chiếu tới một String hợp lệ; phương thức không có hợp đồng chuyển null thành văn bản.

Ví dụ cơ bản:

~~~java
String first = "Java";
String result = first.concat(" 17");

System.out.println(first);  // Java
System.out.println(result); // Java 17
~~~

Biến first vẫn tham chiếu tới String có nội dung "Java". concat() tạo/trả về giá trị kết quả; muốn dùng nội dung đã nối, phải giữ giá trị trả về.

Nếu tham số là String rỗng, nội dung không đổi:

~~~java
String value = "Java";
String result = value.concat("");

System.out.println(result);       // Java
System.out.println(value.equals(result)); // true
~~~

Theo API của String.concat(), nếu đối số có độ dài 0, phương thức trả về chính String nhận lời gọi. Tuy vậy, khi so sánh **nội dung**, hãy ưu tiên equals() thay vì dựa vào toán tử == để quyết định giá trị chuỗi bằng nhau.

### Điều gì xảy ra nếu đối số null?

~~~java
String text = "Hello";
String extra = null;

String result = text.concat(extra); // NullPointerException
~~~

Đây là **đoạn mã minh họa lỗi**. Vấn đề không phải chuỗi text không hợp lệ: receiver text là một String bình thường. Chính đối số extra không cung cấp String để nối; concat() không coi null là chuỗi rỗng và cũng không tự viết ra chữ "null".

**Nguyên tắc:** tham số của concat() phải là String không-null. Nếu nguồn dữ liệu nullable, hãy xử lý trước khi gọi.

## 2. So sánh với toán tử + và +=

Trong ngữ cảnh có một toán hạng là String, toán tử **+** dùng cơ chế nối chuỗi của Java. Các toán hạng không phải String được chuyển thành biểu diễn String; với **tham chiếu null**, biểu diễn là **"null"**.

~~~java
String first = "Java";
String missing = null;

System.out.println(first + missing); // Javanull
System.out.println(missing + first); // nullJava
System.out.println("Value: " + missing); // Value: null
~~~

Toán tử + không gọi **missing.concat(...)**. Vì vậy, việc biến missing null **không làm phép cộng chuỗi ở trên ném NullPointerException**.

Nhưng điều này không bảo đảm ứng dụng đã xử lý đúng dữ liệu. Ví dụ **"Hello null"** có thể gây hiểu nhầm nếu "null" vốn biểu thị không có tên khách hàng.

### += cũng sử dụng quy tắc nối bằng +

~~~java
String message = "Hello";
String name = null;

message += " " + name;
System.out.println(message); // Hello null
~~~

Biểu thức gán nối **+=** tương đương về ý nghĩa với tạo kết quả nối rồi gán lại biến. Nó không biến String thành mutable và không tự kiểm tra null.

So sánh:

| Biểu thức | Khi phần tham chiếu null | Kết quả |
|---|---|---|
| **"A".concat((String) null)** | null là đối số của concat | NullPointerException |
| **"A" + (String) null** | null tham gia phép nối chuỗi | "Anull" |
| **(String) null + "A"** | null tham gia phép nối chuỗi | "nullA" |
| **"A" + 42** | Số được chuyển thành String | "A42" |
| **"A".concat("42")** | Đối số là String hợp lệ | "A42" |
| **"A".concat("")** | Đối số là String rỗng | "A" |
| **"A" + ""** | Phép nối có một chuỗi rỗng | "A" |

Toán tử + chấp nhận nhiều kiểu giá trị khi nối với String; concat() nhận **String**. Viết **"A".concat(42)** không hợp lệ về kiểu ở thời điểm biên dịch, trong khi **"A" + 42** là hợp lệ.

### Không nhầm nối chuỗi với cộng số

~~~java
System.out.println("Total: " + 1 + 2);   // Total: 12
System.out.println("Total: " + (1 + 2)); // Total: 3
~~~

Biểu thức + được đánh giá theo thứ tự và kiểu toán hạng. Khi quá trình đã thành nối chuỗi, các toán hạng số tiếp theo được chuyển thành văn bản. Dùng ngoặc để yêu cầu phép cộng số học trước khi nối.

## 3. Phân biệt null ở vị trí receiver và null ở vị trí đối số

Hai biểu thức sau đều ném NullPointerException, nhưng không cùng nguyên nhân:

~~~java
String first = "Hello";
String missing = null;

first.concat(missing);       // Receiver tồn tại, đối số null
missing.concat(" World");    // Receiver null, không gọi được instance method
~~~

Trong dòng đầu, String.concat() cần một String đối số nhưng nhận null. Trong dòng thứ hai, lời gọi phương thức instance không có đối tượng nhận.

Điều này quan trọng khi bạn viết xử lý đầu vào:

~~~java
static String unsafeConcat(String left, String right) {
    return left.concat(right);
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Nó yêu cầu **cả left lẫn right đều không-null**; chỉ kiểm tra right là chưa đủ nếu left có thể null.

Ngược lại, với biểu thức:

~~~java
static String stringifyWithPlus(String left, String right) {
    return left + right;
}
~~~

Java có thể tạo một String kết quả khi một hoặc cả hai tham chiếu null, chẳng hạn **null + null** trong hai biến kiểu String cho ra chữ **"nullnull"**. Nhưng đó chỉ là quy tắc biểu diễn tham chiếu khi nối, không phải chính sách kiểm tra hợp lệ của dữ liệu.

**Cẩn trọng khi phân tích lỗi:** một chuỗi đã nối thành "null" không cho biết chắc phần tử ban đầu là null hay người dùng thật sự đã nhập bốn ký tự n-u-l-l. Muốn giữ được thông tin này, cần quản lý null trước bước chuyển thành văn bản.

## 4. Chương trình Java 17+ độc lập: quan sát mọi trường hợp

Lưu thành tệp **StringConcatNullDemo.java**:

~~~java
import java.util.Objects;

public class StringConcatNullDemo {
    public static void main(String[] args) {
        String left = "Java";
        String right = null;

        System.out.println("concat-ok=" + left.concat(" 17"));
        System.out.println("plus-right-null=" + (left + right));
        System.out.println("plus-left-null=" + (right + left));

        try {
            left.concat(right);
        } catch (NullPointerException ex) {
            System.out.println("concat-null-argument=NPE");
        }

        try {
            right.concat(" 17");
        } catch (NullPointerException ex) {
            System.out.println("concat-null-receiver=NPE");
        }

        StringBuilder builder = new StringBuilder("Java");
        builder.append((String) null);
        System.out.println("builder-append-null=" + builder);

        System.out.println("fallback-empty="
                + left.concat(Objects.toString(right, "")));
        System.out.println("explicit-value-of="
                + String.valueOf((Object) right));

        String original = "J";
        original.concat("ava");
        System.out.println("ignored-result=" + original);
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac StringConcatNullDemo.java
java StringConcatNullDemo
~~~

Đầu ra chính xác:

~~~text
concat-ok=Java 17
plus-right-null=Javanull
plus-left-null=nullJava
concat-null-argument=NPE
concat-null-receiver=NPE
builder-append-null=Javanull
fallback-empty=Java
explicit-value-of=null
ignored-result=J
~~~

**Giải thích theo dòng:**

1. **concat-ok** là trường hợp cả receiver và tham số String đều hợp lệ.
2. **plus-right-null** và **plus-left-null** minh họa + chuyển tham chiếu null thành chữ "null", bất kể nó nằm trước hay sau chuỗi còn lại.
3. Hai dòng **...=NPE** xuất hiện vì hai lỗi NullPointerException được bắt riêng; chương trình không dừng giữa chừng.
4. **StringBuilder.append((String) null)** có hợp đồng riêng và nối chữ "null". Điều này không làm String.concat(null) trở nên hợp lệ.
5. **Objects.toString(right, "")** chuyển null thành chuỗi rỗng theo chính sách đã chỉ định, nên việc gọi concat() sau đó an toàn.
6. **String.valueOf((Object) right)** minh họa chuyển Object null thành chuỗi "null" một cách tường minh.
7. **ignored-result=J** chứng minh String.concat() không thay đổi đối tượng String đã tồn tại.

Việc in **NPE** là chữ do khối catch quyết định, không phải toàn bộ thông báo ngoại lệ tự sinh từ JVM. Nội dung message của NullPointerException có thể khác nhau; không nên dựa vào nó khi cần output ổn định.

## 5. Xử lý null có chủ đích: bốn chính sách phổ biến

Trước khi nối dữ liệu nullable, hãy lựa chọn rõ: **từ chối**, **coi như rỗng**, **dùng nhãn mặc định**, hay **giữ trạng thái vắng mặt**. Mỗi chính sách phù hợp với yêu cầu khác nhau.

### 5.1. Từ chối null nếu dữ liệu bắt buộc

Nếu cả hai phần phải có giá trị:

~~~java
import java.util.Objects;

public class StrictConcatDemo {
    static String joinRequired(String left, String right) {
        Objects.requireNonNull(left, "left is required");
        Objects.requireNonNull(right, "right is required");
        return left.concat(right);
    }

    public static void main(String[] args) {
        System.out.println(joinRequired("Java", " 17"));

        try {
            joinRequired("Java", null);
        } catch (NullPointerException ex) {
            System.out.println("Missing right");
        }
    }
}
~~~

Lưu **StrictConcatDemo.java**, chạy:

~~~bash
javac StrictConcatDemo.java
java StrictConcatDemo
~~~

Output:

~~~text
Java 17
Missing right
~~~

**Ưu điểm:** không âm thầm tạo chuỗi "Javanull" hoặc che giấu dữ liệu thiếu. Với đầu vào đến từ người dùng, hệ thống thường nên chuyển lỗi thành thông báo validation phù hợp thay vì để ngoại lệ không được xử lý lan ra giao diện.

### 5.2. Coi null là chuỗi rỗng

Nếu phần tùy chọn vắng mặt tương đương không thêm gì:

~~~java
static String appendOptional(String base, String extra) {
    if (base == null) {
        throw new IllegalArgumentException("base is required");
    }
    return base.concat(extra == null ? "" : extra);
}
~~~

Đây là **phương thức minh họa** để đặt bên trong lớp Java. Nếu base="Java" và extra=null, kết quả là "Java". Nếu extra=" 17", kết quả là "Java 17".

Một lựa chọn khác là **Objects.toString(extra, "")**, nhưng dùng toán tử ba ngôi thể hiện rõ rằng extra có kiểu String và null được đổi thành một String rỗng.

**Không đồng nhất null và chuỗi rỗng nếu nghiệp vụ phân biệt hai trạng thái này**, chẳng hạn trong cập nhật từng phần dữ liệu.

### 5.3. Dùng văn bản mặc định có ý nghĩa

Nếu giao diện yêu cầu một nhãn thay thế, ví dụ khách chưa có tên:

~~~java
String customerName = null;
String shownName = customerName == null ? "(unknown)" : customerName;
String greeting = "Hello, ".concat(shownName);

System.out.println(greeting); // Hello, (unknown)
~~~

Văn bản **"(unknown)"** là quyết định thiết kế, không phải quy tắc tự động của concat(). Một số ứng dụng chọn "Guest", "N/A" hoặc bỏ hẳn phần thông tin; cần thống nhất với yêu cầu sản phẩm và ngôn ngữ giao diện.

### 5.4. Giữ null như một trạng thái, chưa nối vội

Khi null mang nghĩa “chưa có dữ liệu”, có thể trả về null hoặc một kiểu thể hiện sự vắng mặt, chỉ nối khi các điều kiện thỏa:

~~~java
static String combineIfPresent(String left, String right) {
    if (left == null || right == null) {
        return null;
    }
    return left.concat(right);
}
~~~

Đây là **phương thức minh họa**. Nó khác chính sách chuyển null thành chuỗi rỗng: thiếu một trong hai phần làm cho **toàn bộ kết quả không có giá trị**, thay vì trả về phần còn lại.

Không có một nhánh xử lý null đúng cho mọi ứng dụng. Điều quan trọng là có **quy tắc minh bạch và nhất quán**.

## 6. Khác biệt giữa concat(), +, StringBuilder.append() và String.join()

Các API này phục vụ các tình huống nối chuỗi tương tự nhưng **không có hợp đồng null giống hệt nhau**:

| Cách nối | Đầu vào | Hành vi với null | Dùng khi |
|---|---|---|---|
| **left.concat(right)** | Cả hai cần là String | Receiver null hoặc đối số null → NullPointerException | Đã xác nhận các phần String bắt buộc hợp lệ |
| **left + right** với ngữ cảnh nối String | Nhiều kiểu giá trị | Tham chiếu null chuyển thành "null" | Nối vài phần ngắn, xây thông báo khi biểu diễn null được kiểm soát |
| **StringBuilder.append((String) value)** | Giá trị String | Đối số String null được thêm chữ "null" | Xây văn bản theo nhiều bước; cần xử lý null trước nếu không muốn chữ "null" |
| **String.join(", ", elements...)** | Dấu phân cách và các phần String | Phần tử null được thêm chữ "null"; delimiter null gây NullPointerException | Nối danh sách phần tử với dấu phân cách |
| **String.valueOf((Object) value)** | Object | Object null → "null" | Chuyển thành biểu diễn văn bản một cách tường minh |
| **Objects.toString(value, fallback)** | Object và chuỗi fallback | value null → dùng fallback | Lựa chọn chuỗi mặc định do ứng dụng quy định |

Ví dụ StringBuilder:

~~~java
StringBuilder sb = new StringBuilder("Hello");
String name = null;

sb.append(" ");
sb.append(name);
System.out.println(sb); // Hello null
~~~

**StringBuilder không đồng nghĩa với concat()** về chính sách null, dù cả hai đều có thể được dùng để ghép văn bản. Ngoài ra, StringBuilder là **mutable**: append() thay đổi nội dung bộ đệm, khác với String.concat() vốn trả về String mà không thay đổi đối tượng gốc.

**Lưu ý về overload:** StringBuilder có nhiều phương thức append() nhận các kiểu khác nhau. Ví dụ **append((char[]) null)** không có cùng hành vi với **append((String) null)** và có thể ném NullPointerException. Khi cần phân tích chính xác null, phải xét **kiểu tham số và overload được chọn**, không chỉ tên hàm.

### Tránh hiểu nhầm String.valueOf(null)

Phương thức String.valueOf() có nhiều overload, trong đó có **valueOf(Object)** và **valueOf(char[])**. Viết trực tiếp **String.valueOf(null)** có thể chọn overload **char[]** và ném NullPointerException, thay vì tạo chữ "null".

Do đó, khi muốn minh họa rõ quy tắc **Object null → "null"**, hãy dùng **String.valueOf((Object) null)**. Hoặc nếu mục tiêu là thay thế null thành rỗng/nhãn khác, dùng Objects.toString(value, fallback) và chọn fallback rõ ràng.

### String.join() không tự bỏ qua phần tử null

~~~java
System.out.println(String.join(", ", "A", null, "B")); // A, null, B
~~~

Nếu nghiệp vụ muốn **bỏ qua** phần tử null, phải lọc hoặc quy định cách xử lý trước khi gọi. Không nên đoán API nào cũng ngầm bỏ null để tiện trình bày.

## 7. So sánh với "null" và chuỗi rỗng: vấn đề dữ liệu, không chỉ cú pháp

Ba giá trị sau khác nhau:

~~~java
String missing = null;
String empty = "";
String literal = "null";
~~~

- **missing**: tham chiếu không trỏ đến String.
- **empty**: String tồn tại, dài 0.
- **literal**: String có bốn ký tự n, u, l, l.

Bởi vậy:

~~~java
System.out.println(missing == null);         // true
System.out.println("".equals(missing));      // false
System.out.println("null".equals(literal));  // true
System.out.println("null".equals(missing));  // false
~~~

Sau khi thực hiện **"prefix" + missing**, kết quả chứa bốn chữ "null" giống như khi nối **"prefix" + literal**. Nếu chỉ giữ String kết quả, thông tin ban đầu có phải null hay không đã bị mất.

Trong ứng dụng thực tế, điều này có thể dẫn đến lỗi như:

- **Tên hiển thị:** "Hello null" thay vì "Hello Guest".
- **Đường dẫn:** "/users/null" tạo địa chỉ trông hợp lệ nhưng dựa trên dữ liệu thiếu.
- **Khóa cache hoặc mã định danh:** giá trị thiếu và giá trị chữ "null" bị gom vào cùng một khóa sau khi chuyển thành String.
- **Log và thông báo:** văn bản chứa "null" không đủ để phân biệt tham chiếu null với giá trị người dùng nhập.

Nếu phải giữ ngữ nghĩa dữ liệu, hãy **kiểm tra null trước khi chuyển thành văn bản**, hoặc lưu cấu trúc dữ liệu gồm giá trị và trạng thái rõ ràng.

## 8. Có nên dùng concat() thay cho + để tối ưu hiệu năng?

`concat()` không mặc nhiên nhanh hơn `+`. Với một vài thành phần, `+` thường rõ ý và compiler/JVM hiện đại có thể tối ưu. Với quá trình tích lũy nhiều lượt, `StringBuilder` giúp xây dựng kết quả trong bộ đệm mutable. Bài **Nối trong một biểu thức so với tích lũy qua vòng lặp** giải thích lựa chọn và đo hiệu năng; tại đây nên ưu tiên **hợp đồng null** khi quyết định gọi `concat`.

## 9. Phân tích tình huống thực tế: xây lời chào từ tên tùy chọn

Giả sử API trả về tên khách có thể null:

~~~java
String nameFromApi = null;
~~~

Ba cách viết có ý nghĩa khác nhau:

~~~java
String unsafe = "Hello, " + nameFromApi;
// unsafe: "Hello, null"

String safeDisplay = "Hello, "
        + (nameFromApi == null ? "Guest" : nameFromApi);
// safeDisplay: "Hello, Guest"

// "Hello, ".concat(nameFromApi) sẽ ném NullPointerException.
~~~

Đây là **mã minh họa**, không phải ba phương án tương đương nghiệp vụ. Nếu người dùng có tên rỗng hoặc chỉ có whitespace, cả điều kiện **nameFromApi == null** vẫn chưa đủ. Có thể cần:

~~~java
static String greeting(String name) {
    String display = name == null || name.isBlank()
            ? "Guest"
            : name.strip();
    return "Hello, ".concat(display);
}
~~~

Hàm này định nghĩa rõ: null, rỗng hoặc chỉ whitespace đều thành "Guest"; tên có nội dung được strip() ở hai đầu. Nó phù hợp khi **hợp đồng UI cho phép** xử lý như vậy. Nếu khoảng trắng là thông tin quan trọng, không được tự strip.

Phương thức **greeting()** ở trên là minh họa và cần đặt trong một lớp Java khi biên dịch.

## 10. Lỗi phổ biến cần tránh

- `concat(null)` ném `NullPointerException`, còn `"A" + (String) null` cho `"Anull"`.
- `left.concat(right)` yêu cầu **cả receiver và đối số** khác `null`.
- `concat()` trả kết quả, không sửa chuỗi cũ; lời gọi mà bỏ kết quả không đổi giá trị biến.
- `concat(String)` không nhận trực tiếp `int` hay một đối tượng tùy ý, khác với `+` trong ngữ cảnh nối chuỗi.
- `String.valueOf(null)` phải xét overload: ép `(Object) null` khi cần đúng hợp đồng `valueOf(Object)`.
- Trước khi dựng hiển thị, khóa, URL, SQL hoặc log, xác định chính sách dữ liệu thiếu; dùng prepared statement cho SQL và serializer phù hợp cho dữ liệu cấu trúc.

**Trọng tâm:** null và chữ `"null"` là hai trạng thái khác nhau; cần quyết định trước khi tạo văn bản.

## 11. Bài tập và đáp án

Xét đoạn sau:

~~~java
String a = "A";
String b = null;
String c = "";
~~~

Hãy tự trả lời trước khi xem đáp án:

1. **a.concat(c)** trả về nội dung gì?
2. **a.concat(b)** tạo kết quả hay ném ngoại lệ?
3. **a + b** có nội dung gì?
4. **b + a** có nội dung gì?
5. **a + c** khác **a.concat(c)** về nội dung không?
6. Nếu gọi **b.concat(a)** thì có khác nguyên nhân lỗi ở câu 2 không?
7. Khi nào nên sử dụng **Objects.toString(b, "")**?
8. Nếu cần phân biệt null với chuỗi có nội dung "null", có nên nối bằng + ngay từ đầu không?

**Đáp án:**

1. **"A"**: nối String rỗng không thêm ký tự nào.
2. **NullPointerException**: đối số của concat() là null.
3. **"Anull"**: toán tử + chuyển tham chiếu null thành chữ "null".
4. **"nullA"**: null cũng được chuyển thành "null" khi ở phía trước.
5. **Không khác về nội dung**, đều là "A"; không nên dựa vào danh tính tham chiếu để so nội dung.
6. **Có**: câu 2 lỗi vì đối số null; b.concat(a) lỗi vì receiver null.
7. Khi **có chủ đích** muốn coi null là String rỗng trước khi nối, không phải khi nghiệp vụ cần bảo toàn trạng thái vắng mặt.
8. **Không nên**, nếu kết quả cần giữ thông tin null thật. Hãy quyết định chính sách hoặc giữ dữ liệu có cấu trúc trước khi biểu diễn thành văn bản.

**Ghi nhớ:** **concat(null) → NullPointerException; nối String bằng + với tham chiếu null → chữ "null"**. Đối với dữ liệu thật, hãy kiểm tra receiver, đối số và chính sách xử lý null trước khi nối; đồng thời sử dụng kết quả trả về của concat() vì String là bất biến.
