# Lời gọi với `null` và lỗi lựa chọn phương thức không rõ ràng trong Java

Khi một class có nhiều phương thức cùng tên (**method overloading**), Java chọn phương thức cần gọi dựa trên **tên, số lượng đối số, kiểu đối số và các quy tắc overload resolution ở thời điểm biên dịch**. Một tình huống dễ gây nhầm lẫn là gọi phương thức bằng literal `null`:

~~~java
print(null);
~~~

`null` có thể được chuyển thành nhiều kiểu tham chiếu, nhưng không thể chuyển trực tiếp thành kiểu nguyên thủy như `int`. Nếu có một overload phù hợp rõ ràng nhất, compiler chọn nó. Nếu có từ hai overload cùng áp dụng mà không tồn tại một lựa chọn cụ thể nhất theo các quy tắc Java, chương trình **không biên dịch** và thường báo lỗi dạng `reference to print is ambiguous`.

Bài học này tập trung vào **lời gọi với `null` và cách xử lý overload mơ hồ**, gồm quan hệ kế thừa, interface, array, varargs, boxing, cast và các quyết định thiết kế API. Các chương trình độc lập dùng cú pháp tương thích Java 17+.

## 1. Kiến thức cần có: nạp chồng phương thức là gì?

Hai phương thức là **overload** khi được khai báo với cùng tên trong phạm vi kiểu phù hợp nhưng có danh sách tham số khác nhau theo quy tắc chữ ký Java:

~~~java
static void log(String text) {
    System.out.println("String: " + text);
}

static void log(Integer number) {
    System.out.println("Integer: " + number);
}
~~~

Đây là đoạn minh họa đặt trong một class; bản thân đoạn không có `main`. `log("hello")` dùng phiên bản `String`; `log(Integer.valueOf(5))` dùng phiên bản `Integer`. Nhưng `log(null)` có vấn đề: cả `String` và `Integer` đều là kiểu tham chiếu phù hợp với null, trong khi không kiểu nào là subtype của kiểu còn lại. Không có một overload cụ thể hơn để chọn, nên lời gọi **mơ hồ tại thời điểm biên dịch**.

**Lưu ý:**

- Không thể overload chỉ bằng **khác tên tham số**. `log(String text)` và `log(String message)` có cùng chữ ký.
- Không thể overload chỉ bằng **kiểu trả về**. `int load(String)` và `String load(String)` không thể cùng tồn tại chỉ vì trả kiểu khác.
- Overloading khác **overriding**: overloading chọn chữ ký theo thông tin compile time, còn overriding của instance method chọn triển khai phù hợp với runtime receiver sau khi chữ ký đã được xác định.
- Literal `null` khác với chuỗi `"null"`, số `0` hoặc tham chiếu `new Object()`.

## 2. `null` có kiểu gì và vì sao nhiều overload cùng phù hợp?

Java có **null literal** (`null`). Biểu thức này thuộc *null type* theo đặc tả ngôn ngữ, một kiểu đặc biệt không có tên để khai báo biến thông thường. Giá trị null có thể gán cho biến thuộc **kiểu tham chiếu** và có thể dùng làm argument cho tham số kiểu tham chiếu tương thích.

Ví dụ:

~~~java
String name = null;
Integer count = null;
Object unknown = null;
CharSequence text = null;
int[] numbers = null;
Runnable task = null;
~~~

Các phép gán trên hợp lệ. Trong khi đó:

~~~java
int count = null;       // Lỗi biên dịch.
boolean ready = null;   // Lỗi biên dịch.
~~~

Đây là **ví dụ lỗi biên dịch**, không phải mã để ghép vào chương trình chạy. Kiểu `int` và `boolean` là primitive, không thể giữ giá trị null.

Một lời gọi `method(null)` **không có thông tin kiểu tham chiếu cụ thể từ chính literal** để thu hẹp lựa chọn xuống `String` hay `Integer`. Nếu compiler nhìn thấy cả hai chữ ký đều áp dụng, nó cần sử dụng các quy tắc chọn phương thức cụ thể hơn.

## 3. Trường hợp dễ nhất: `Object` và `String`

Tạo file **`NullMostSpecificDemo.java`**:

~~~java
public class NullMostSpecificDemo {
    static void print(Object value) {
        System.out.println("Object");
    }

    static void print(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        print(null);
        print("Java");

        String text = null;
        print(text);

        Object unknown = null;
        print(unknown);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NullMostSpecificDemo.java
java NullMostSpecificDemo
~~~

Stdout:

~~~text
String
String
String
Object
~~~

### Vì sao `print(null)` chọn `print(String)`?

- `null` phù hợp với cả tham số `Object` và `String`.
- `String` là subtype của `Object`.
- Trong trường hợp này, `print(String)` **cụ thể hơn** `print(Object)`, nên compiler chọn phiên bản `String`.
- Nếu `text` được **khai báo là `String`** nhưng mang giá trị null, `print(text)` vẫn chọn `print(String)`.
- Nếu biến `unknown` được **khai báo là `Object`**, `print(unknown)` chọn `print(Object)`, dù giá trị runtime của biến là null.

Đây là quy tắc quan trọng: **overload resolution dùng kiểu tại thời điểm biên dịch của biểu thức argument, không chạy thử giá trị runtime rồi chọn lại chữ ký**.

### Bảng dự đoán nhanh

Với hai overload `print(Object)` và `print(String)`:

| Lời gọi | Chọn overload | Lý do |
| --- | --- | --- |
| `print(null)` | `String` | Cả hai hợp lệ; `String` cụ thể hơn |
| `print("hello")` | `String` | Đối số có kiểu `String` |
| `String s = null; print(s);` | `String` | Kiểu khai báo của `s` là `String` |
| `Object o = null; print(o);` | `Object` | Không có chuyển đổi gán tự động `Object → String` |
| `print((Object) null)` | `Object` | Cast xác định kiểu biểu thức là `Object` |
| `print((String) null)` | `String` | Cast xác định kiểu biểu thức là `String` |

Với `print((Object) null)`, việc chọn `Object` không xảy ra vì object thực tế thay đổi. Cả hai biểu thức vẫn mang **giá trị null**; cast thay đổi thông tin **kiểu tại compile time** dùng cho overload resolution.

## 4. Khi hai tham số là các kiểu không có quan hệ subtype

Xét class:

~~~java
class Printer {
    static void print(String text) {
        System.out.println("String");
    }

    static void print(Integer number) {
        System.out.println("Integer");
    }
}
~~~

Đây là khai báo class hợp lệ nhưng chưa có `main`. `String` không kế thừa `Integer` và `Integer` không kế thừa `String`. Bởi vậy:

~~~java
Printer.print(null); // Lỗi biên dịch: reference to print is ambiguous.
~~~

Đoạn lời gọi trên được đánh dấu **cố ý không biên dịch**. Chỉ nhìn vào giá trị null, Java không có cơ sở để ưu tiên String hay Integer. Thứ tự khai báo hai method và thứ tự chúng xuất hiện trong file **không quyết định** lựa chọn.

### Cách sửa 1: truyền giá trị có kiểu

~~~java
Printer.print("hello");               // Chọn String.
Printer.print(Integer.valueOf(42));   // Chọn Integer.
~~~

Nếu logic thực tế là in chuỗi thì truyền chuỗi; nếu là số nguyên kiểu wrapper thì truyền giá trị tương ứng. Đây là cách rõ nghĩa nhất khi caller đã có dữ liệu.

### Cách sửa 2: cast `null` để xác định overload chủ đích

~~~java
Printer.print((String) null);   // Chọn String.
Printer.print((Integer) null);  // Chọn Integer.
~~~

Cast làm **kiểu biểu thức đối số** là String hoặc Integer. Khi đó chỉ overload tương ứng nhận tham số có kiểu phù hợp. Trong ví dụ này không có mơ hồ nữa.

**Cảnh báo:** Cast null chỉ giải quyết vấn đề **biên dịch**. Nếu thân method gọi `text.length()` hoặc unbox `Integer` mà không kiểm tra null, chương trình vẫn có thể ném `NullPointerException` lúc chạy. Một API tốt cần quyết định và nêu rõ liệu null có hợp lệ.

### Cách sửa 3: biến có kiểu tường minh

~~~java
String text = null;
Integer number = null;

Printer.print(text);
Printer.print(number);
~~~

Những biến được khai báo kiểu rõ ràng cho phép compiler chọn đúng overload. Cách này hữu ích khi null biểu thị dữ liệu chưa có, nhưng vẫn cần chính sách xử lý null bên trong method.

## 5. Ví dụ hoàn chỉnh: mơ hồ và cách sửa bằng cast

Tạo file **`AmbiguousNullSolutionDemo.java`**:

~~~java
public class AmbiguousNullSolutionDemo {
    static void describe(String value) {
        System.out.println("String=" + value);
    }

    static void describe(Integer value) {
        System.out.println("Integer=" + value);
    }

    public static void main(String[] args) {
        // describe(null); // Cố ý bỏ chú thích sẽ gây lỗi ambiguous.

        describe((String) null);
        describe((Integer) null);
        describe("Java");
        describe(Integer.valueOf(7));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AmbiguousNullSolutionDemo.java
java AmbiguousNullSolutionDemo
~~~

Stdout:

~~~text
String=null
Integer=null
String=Java
Integer=7
~~~

Từng method chỉ nối chuỗi để có thể hiển thị null mà không dereference. Vì vậy lời gọi đã chọn overload có thể chạy bình thường; nếu thay bằng `value.length()` hoặc `value.intValue()` thì null làm phát sinh exception.

Nếu bỏ chú thích dòng `describe(null);`, compiler báo mơ hồ **trước khi tạo chương trình để chạy**, cho dù cả hai implementation đang có vẻ in đúng “null”. Compiler không chạy thử thân method để quyết định một nhánh thuận tiện.

## 6. Có ba overload: thêm `Object` không nhất thiết loại bỏ mơ hồ

Giả sử:

~~~java
static void write(Object value) {
    System.out.println("Object");
}

static void write(String value) {
    System.out.println("String");
}

static void write(Integer value) {
    System.out.println("Integer");
}
~~~

Đây là ba method minh họa đặt trong cùng class. Lời gọi `write(null)` vẫn **mơ hồ** vì:

1. `Object`, `String` và `Integer` đều áp dụng.
2. `String` và `Integer` đều cụ thể hơn `Object`.
3. Giữa `String` và `Integer` không có quan hệ subtype.
4. Không có một phương thức cụ thể nhất duy nhất.

Compiler **không** chọn `Object` để “tránh xung đột”. Thêm một overload tổng quát thường làm danh sách ứng viên nhiều hơn, chứ không tạo ra quy tắc ưu tiên mặc định.

Các lời gọi được phân biệt rõ:

~~~java
write((Object) null);    // Object
write((String) null);    // String
write((Integer) null);   // Integer
~~~

Khi thiết kế API public, hãy kiểm tra cả trường hợp caller truyền null literal. Thêm một overload nhận tham chiếu mới có thể biến lời gọi `write(null)` trước kia hợp lệ thành **lỗi biên dịch** ở source code của khách hàng.

## 7. Interface và quan hệ subtype: cần xét toàn bộ cây kiểu

Các overload không nhất thiết nhận class; interface cũng là kiểu tham chiếu và có thể dẫn đến mơ hồ.

Ví dụ:

~~~java
static void view(CharSequence value) {
    System.out.println("CharSequence");
}

static void view(String value) {
    System.out.println("String");
}
~~~

Vì `String` implements `CharSequence`, lời gọi `view(null)` chọn overload `String`. Đây là trường hợp có quan hệ subtype rõ ràng.

Nhưng:

~~~java
static void view(CharSequence value) {
    System.out.println("CharSequence");
}

static void view(java.io.Serializable value) {
    System.out.println("Serializable");
}
~~~

Với hai overload sau:

- `view(null)` **mơ hồ** vì cả `CharSequence` và `Serializable` đều là kiểu tham chiếu, nhưng không interface nào là subtype của interface kia.
- `view("Java")` cũng **mơ hồ** trong bộ hai overload này: đối số `String` implements cả hai interface, không có phương thức nào cụ thể hơn.
- `view((CharSequence) null)` chọn `CharSequence`; `view((java.io.Serializable) null)` chọn `Serializable`.
- **`view((String) null)` vẫn mơ hồ**, vì một giá trị có kiểu compile time là `String` có thể chuyển thành **cả hai interface** và việc cast sang String không khiến một interface cụ thể hơn interface kia.

Điểm cuối đặc biệt quan trọng: **cast đến một kiểu cụ thể không phải luôn giải quyết được ambiguity**. Cast chỉ giúp khi nó thay đổi tập phương thức áp dụng hoặc mức độ cụ thể để còn một phương thức thắng thế.

### Ví dụ chạy độc lập với interface

Lưu file **`InterfaceNullDemo.java`**:

~~~java
public class InterfaceNullDemo {
    static void show(CharSequence value) {
        System.out.println("CharSequence");
    }

    static void show(java.io.Serializable value) {
        System.out.println("Serializable");
    }

    public static void main(String[] args) {
        // show(null);          // Mơ hồ.
        // show("Java");        // Cũng mơ hồ.
        // show((String) null); // Vẫn mơ hồ.

        show((CharSequence) null);
        show((java.io.Serializable) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceNullDemo.java
java InterfaceNullDemo
~~~

Stdout:

~~~text
CharSequence
Serializable
~~~

Một lựa chọn thiết kế khác là đặt hai tên method khác nhau, ví dụ `showCharacters(CharSequence)` và `showSerializable(Serializable)`, khi hai hành vi thực sự không giống nhau. Cách này tránh phải yêu cầu người gọi cast chỉ để compiler biết ý định.

## 8. `null` và mảng: mảng cũng là kiểu tham chiếu

`String[]`, `Integer[]`, `int[]` và mọi kiểu array khác đều là object type, nên một tham số kiểu mảng có thể nhận null.

~~~java
static void inspect(String[] values) {
    System.out.println("String[]");
}

static void inspect(Integer[] values) {
    System.out.println("Integer[]");
}
~~~

`inspect(null)` mơ hồ vì hai array type khác nhau và không có quan hệ subtype giữa `String[]` và `Integer[]`. Có thể chọn tường minh:

~~~java
inspect((String[]) null);
inspect((Integer[]) null);
~~~

Nếu có `inspect(Object)` và `inspect(String[])`, `inspect(null)` chọn `String[]` vì mọi array đều là subtype của `Object`.

Chú ý cách phân biệt hai tình huống:

- `inspect((String[]) null)`: **chính tham chiếu mảng là null**.
- `inspect(new String[] {null})`: có **một object mảng thật** chứa **một phần tử null**.

Hai giá trị này có kiểu compile time tương thích với `String[]` nhưng khác hoàn toàn ở runtime. `values.length` trên mảng null gây `NullPointerException`; với mảng một phần tử null, `values.length` là 1.

## 9. `null` và varargs: một null có thể là mảng hoặc một phần tử

Một tham số varargs như `String... names` thực chất được dùng như một mảng `String[]` trong thân method.

~~~java
static void printNames(String... names) {
    if (names == null) {
        System.out.println("array is null");
    } else {
        System.out.println("length=" + names.length);
    }
}
~~~

Đây là đoạn method minh họa. Hai lời gọi dưới đây có nghĩa khác nhau:

~~~java
printNames((String[]) null); // Truyền một tham chiếu mảng null.
printNames((String) null);   // Truyền một phần tử String null.
~~~

Ở lời gọi thứ nhất, parameter `names` là null. Ở lời gọi thứ hai, cơ chế varargs đóng gói một phần tử `String` mang giá trị null vào mảng; `names.length` là 1.

### Chương trình hoàn chỉnh

Lưu file **`VarargsNullDemo.java`**:

~~~java
public class VarargsNullDemo {
    static void printNames(String... names) {
        if (names == null) {
            System.out.println("array is null");
            return;
        }

        System.out.println("length=" + names.length);
        if (names.length > 0) {
            System.out.println("first=" + names[0]);
        }
    }

    public static void main(String[] args) {
        printNames((String[]) null);
        printNames((String) null);
        printNames();
        printNames("An", "Binh");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VarargsNullDemo.java
java VarargsNullDemo
~~~

Stdout:

~~~text
array is null
length=1
first=null
length=0
length=2
first=An
~~~

Lời gọi `printNames(null)` nếu viết không cast được compiler xem như lời gọi không varargs tới `String[]`, vì null chuyển được thành mảng, và thường phát cảnh báo gợi ý cast để phân biệt cách dùng. Trong các trường hợp này, bạn không nên dựa vào ý định “null là một phần tử” khi cú pháp cũng có thể biểu thị **một mảng null**. Viết cast chính xác hoặc một mảng tường minh:

~~~java
printNames(new String[] {null}); // Một mảng có phần tử null.
~~~

### Hai overload varargs cũng có thể gây mơ hồ

~~~java
static void send(String... values) { /* ... */ }
static void send(Integer... values) { /* ... */ }
~~~

`send(null)` mơ hồ khi xét hai array type không có quan hệ subtype. `send()` cũng có thể mơ hồ khi cả hai phiên bản áp dụng với danh sách varargs rỗng. Cách tránh là cho caller chọn một phiên bản bằng đối số có kiểu hoặc thiết kế API không buộc người dùng phân biệt các nhánh bằng kiểu mảng không liên quan.

## 10. Primitive, wrapper, boxing và `null`

Một primitive như `int` không thể nhận null. Nhưng wrapper `Integer` là reference type và có thể nhận null:

~~~java
static void test(int value) {
    System.out.println("int");
}

static void test(Integer value) {
    System.out.println("Integer");
}
~~~

Trong bộ overload này:

- `test(5)` chọn `test(int)` vì argument `5` là `int`.
- `test(Integer.valueOf(5))` chọn `test(Integer)` vì đối số có kiểu `Integer`.
- `test(null)` chọn **`test(Integer)`** vì `int` không nhận null, còn `Integer` nhận được.
- `test((Integer) null)` chọn `Integer`; phương thức đó phải xử lý khả năng null nếu cần.
- `test((int) null)` **không biên dịch**, vì không thể cast trực tiếp null sang primitive `int`.

Nếu chỉ có `test(int)`, lời gọi `test(null)` không có method applicable; thông báo lỗi về kiểu argument không phù hợp, **không phải ambiguity giữa nhiều overload**.

### Ví dụ Java 17+ chạy độc lập

Lưu file **`PrimitiveWrapperNullDemo.java`**:

~~~java
public class PrimitiveWrapperNullDemo {
    static void test(int value) {
        System.out.println("int=" + value);
    }

    static void test(Integer value) {
        System.out.println("Integer=" + value);
    }

    public static void main(String[] args) {
        test(5);
        test(Integer.valueOf(5));
        test(null);
        test((Integer) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrimitiveWrapperNullDemo.java
java PrimitiveWrapperNullDemo
~~~

Stdout:

~~~text
int=5
Integer=5
Integer=null
Integer=null
~~~

Đoạn `"Integer=" + value` chuyển wrapper null thành chuỗi `"null"` trong phép nối chuỗi; code không unbox giá trị này nên không ném `NullPointerException`.

Ngược lại, nếu caller có một biến `Integer x = null;` và truyền vào method **chỉ nhận `int`**, compiler có thể chèn unboxing khi gọi, dẫn đến `NullPointerException` **trước khi thân method được thực thi**. Biên dịch thành công không bảo đảm một giá trị wrapper null có thể dùng an toàn ở nơi cần primitive.

## 11. Vì sao compiler không chọn theo nội dung trong thân method?

Xét:

~~~java
static void parse(String text) {
    if (text == null) {
        System.out.println("No text");
        return;
    }
    System.out.println(text.length());
}

static void parse(Integer number) {
    if (number == null) {
        System.out.println("No number");
        return;
    }
    System.out.println(number.intValue());
}
~~~

Thân cả hai overload đều xử lý null an toàn. Nhưng `parse(null)` vẫn **mơ hồ**.

Java **không duyệt thân method để đoán overload nào hữu ích hơn**, cũng không tự ưu tiên nhánh có catch hay xử lý null. Overload resolution dùng quy tắc kiểu và mức độ applicable trước khi chương trình chạy. Do đó:

- Một overload xử lý null tốt hơn không làm nó được ưu tiên.
- Kiểu trả về cũng không phải công tắc chọn giữa hai phương thức chỉ khác tham số `String`/`Integer` trong lời gọi thông thường.
- Không thể sửa ambiguity bằng cách thay đổi thứ tự khai báo method hoặc di chuyển một overload lên phía trên.
- Có thể cần thay **kiểu biểu thức ở call site**, **tên method**, hoặc **bộ overload**.

Nếu API cần có cách xử lý null thống nhất, một overload chung `parse(Object)` hoặc method `parseMissing()` có thể phù hợp về thiết kế, nhưng phải đánh giá xem điều đó có thay đổi meaning của các lời gọi khác không.

## 12. Overload resolution có các giai đoạn: cố định trước, varargs sau

Java không lấy mọi overload rồi đo một “độ giống nhau” đơn giản. Theo cách nhìn nhập môn, compiler tiến hành những giai đoạn để tìm phương thức áp dụng; đại ý:

1. Tìm những method áp dụng bằng các **chuyển đổi nghiêm ngặt** cho lời gọi arity cố định (không dùng boxing/unboxing).
2. Nếu không có ứng viên thích hợp, xét các chuyển đổi **lỏng hơn** như boxing/unboxing cho arity cố định.
3. Nếu vẫn không có ứng viên phù hợp, xét lời gọi với **varargs**.
4. Trong giai đoạn đầu tiên tìm được các ứng viên applicable, áp dụng quy tắc **most specific**; nếu không xác định được một lựa chọn duy nhất và các quy tắc tie-break không giải quyết được thì báo ambiguity.

Đây là bản tóm tắt thực hành; đặc tả có các quy tắc chi tiết về generic method, subtype, accessibility, variable arity và chữ ký. Điều cần nhớ là **không được tự đặt thứ tự ưu tiên “primitive hơn reference”, “static hơn instance”, hoặc “method khai báo trước thắng”**.

Đối với `null`, nhiều tình huống đã mơ hồ ngay giữa những phương thức nhận kiểu tham chiếu ở giai đoạn đầu. Sự tồn tại của một phương thức varargs khác không tự cứu lời gọi khỏi ambiguity này.

### Trường hợp một overload thừa kế tham số cụ thể hơn

~~~java
static void handle(Object value) { /* ... */ }
static void handle(CharSequence value) { /* ... */ }
static void handle(String value) { /* ... */ }
~~~

`handle(null)` chọn `handle(String)` vì `String <: CharSequence <: Object`. Chuỗi subtype rõ ràng giúp có một ứng viên cụ thể nhất.

Nhưng nếu thay `String` bằng `Integer`:

~~~java
static void handle(Object value) { /* ... */ }
static void handle(CharSequence value) { /* ... */ }
static void handle(Integer value) { /* ... */ }
~~~

`handle(null)` mơ hồ giữa `CharSequence` và `Integer`. `Object` là supertype của cả hai nên không phải lựa chọn cụ thể nhất.

Các đoạn này chỉ minh họa cấu trúc overload, không dùng đồng thời cả sáu method trong một class.

## 13. Vì sao `Object value = null` khác `null` literal?

Ví dụ chạy độc lập, file **`StaticTypeOfArgumentDemo.java`**:

~~~java
public class StaticTypeOfArgumentDemo {
    static void choose(Object value) {
        System.out.println("Object");
    }

    static void choose(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        Object generic = "Java";
        Object missing = null;
        String specific = null;

        choose(generic);
        choose(missing);
        choose(specific);
        choose(null);
        choose((Object) null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTypeOfArgumentDemo.java
java StaticTypeOfArgumentDemo
~~~

Stdout:

~~~text
Object
Object
String
String
Object
~~~

Dù `generic` tại runtime đang tham chiếu đến một `String` thật, compiler vẫn thấy argument có kiểu khai báo `Object` khi chọn overload. `choose(generic)` do đó gọi `choose(Object)`. **Đừng nhầm dynamic dispatch của overriding với compile-time selection của overloading.**

Nếu cần xử lý object theo kiểu runtime, hãy cân nhắc polymorphism và instance method override, pattern matching `instanceof` hoặc các API rõ nghĩa khác thay vì cố tạo một tập overload rồi chờ Java tự đoán runtime type của argument.

### Overloading kết hợp overriding: hai bước độc lập

Có thể có class cha định nghĩa `process(Object)` và `process(String)`, trong khi class con override `process(String)`. Compiler trước tiên chọn chữ ký overload áp dụng dựa trên kiểu tại điểm gọi; nếu chữ ký đó là instance method có override phù hợp, runtime chọn triển khai của object thực tế. **Thay đổi nội dung object hoặc để giá trị null không khiến compiler chọn lại chữ ký overload.**

## 14. Null với generic methods: kiểu suy luận không luôn loại ambiguity

Generic method có thể khiến quá trình chọn overload thêm phức tạp vì compiler suy luận type variables.

Ví dụ minh họa:

~~~java
static <T> void consume(T value) {
    System.out.println("generic");
}

static void consume(String value) {
    System.out.println("String");
}
~~~

Với `consume(null)`, trong ví dụ này overload `String` cụ thể hơn overload generic có thể nhận kiểu thích hợp, nên phiên bản `String` được chọn. Không nên diễn giải rằng mọi generic method đều “thua” method không generic; việc chọn phụ thuộc chữ ký và khả năng áp dụng của từng overload.

Một tình huống khác:

~~~java
static void use(java.util.List<String> values) { /* ... */ }
// Không thể khai báo thêm:
static void use(java.util.List<Integer> values) { /* ... */ }
~~~

Hai chữ ký `use(List<String>)` và `use(List<Integer>)` sau **type erasure** đều có dạng tương ứng `use(List)`, nên **không thể dùng chung làm hai overload riêng** theo cách này. Lỗi xảy ra ngay khi khai báo, trước khi bàn đến `use(null)`.

Khi muốn API xử lý hai loại danh sách, có thể chọn:
- Một method generic xử lý chung khi thao tác thực sự giống nhau.
- Hai tên method rõ nghĩa nếu logic khác nhau.
- Một class/record yêu cầu chứa dữ liệu có kiểu nghiệp vụ riêng.
- Cơ chế phân nhánh có chủ đích bên trong method nếu cần xét kiểu dữ liệu runtime.

### Khi lambda và method reference xuất hiện

Lambda, method reference và generic method invocation có thể là các biểu thức được xét với kiểu mục tiêu (**target typing**). Nếu có nhiều overload nhận những functional interface khác nhau, việc chọn method còn phụ thuộc chữ ký hàm của các interface và quy tắc suy luận. Đặc biệt, việc dùng `null` thay cho một lambda/function object có thể tạo ambiguity mới. Khi gặp lỗi loại này, cách khắc phục thực tế thường là khai báo biến với **functional interface cụ thể**, thêm cast có chủ đích hoặc đặt hai tên method khác nhau.

Không nên cho rằng compiler sẽ chọn một overload chỉ vì thân lambda có vẻ phù hợp với cái tên method. Hãy xác định chữ ký type thực tế.

## 15. Constructor overloading cũng chịu quy tắc với `null`

Không chỉ method thông thường; constructor overload cũng có thể mơ hồ.

~~~java
class Message {
    Message(String text) { /* ... */ }
    Message(Integer code) { /* ... */ }
}
~~~

`new Message(null)` gây lỗi **reference to Message is ambiguous** (cách diễn đạt cụ thể tùy phiên bản compiler). Hai constructor đều áp dụng mà không constructor nào cụ thể hơn.

Cách giải quyết khi cần thử một constructor cụ thể:

~~~java
Message a = new Message((String) null);
Message b = new Message((Integer) null);
~~~

Đây là **đoạn minh họa**, không phải chương trình chạy độc lập. Trong ứng dụng thật, constructor nhận null có thể từ chối ngay bằng validation; cast chỉ giúp chọn đúng constructor.

### Static factory là một lựa chọn thiết kế rõ hơn

Thay vì overload hai constructor với kiểu tham chiếu không liên quan, có thể cung cấp static factory có tên thể hiện ý định:

~~~java
static Message fromText(String text) { /* tạo Message */ }
static Message fromCode(Integer code) { /* tạo Message */ }
~~~

Hai khai báo là **pseudocode API**, chưa có class implementation. Khi caller viết `Message.fromText(null)`, lựa chọn hành vi được thể hiện bằng **tên**, không phụ thuộc compiler đoán kiểu giữa nhiều constructor. Factory còn có thể đặt validation và giá trị mặc định phù hợp với domain.

## 16. `null` khác với chuỗi "null", object rỗng và giá trị mặc định

Một số lỗi thiết kế xuất phát từ việc dùng cùng một giá trị để biểu diễn nhiều trạng thái khác nhau:

| Đối số | Kiểu biểu thức | Ý nghĩa tiềm năng |
| --- | --- | --- |
| `null` | Null type | Không có reference / chưa cung cấp, tùy hợp đồng |
| `"null"` | `String` | Chuỗi gồm bốn ký tự n-u-l-l |
| `""` | `String` | Chuỗi rỗng, là một object chuỗi |
| `new String[0]` | `String[]` | Mảng String rỗng, không phải null |
| `new String[] {null}` | `String[]` | Mảng có một phần tử null |
| `Integer.valueOf(0)` | `Integer` | Object wrapper đại diện số 0 |
| `Optional.empty()` | `Optional<T>` | Một object biểu diễn sự vắng mặt theo API Optional |

Compiler chọn overload theo **kiểu của biểu thức**, không tự hiểu `""` là “thiếu chuỗi” hay `0` là “không có số”. Hợp đồng method mới là nơi quyết định một giá trị có hợp lệ.

Một cách làm rõ khi API có trường dữ liệu không bắt buộc:

~~~java
static String displayName(String name) {
    return name == null || name.isBlank() ? "(unknown)" : name;
}
~~~

Đây là method minh họa; nó chấp nhận null theo quy tắc cụ thể. Nếu null không có ý nghĩa hợp lệ, có thể từ chối sớm bằng `Objects.requireNonNull(name, "name")` thay vì âm thầm chuyển sang tên mặc định.

## 17. Nên sửa overload mơ hồ bằng cách nào?

Có ba lớp giải pháp, từ call site đến thiết kế API.

### Giải pháp A — Làm kiểu đối số rõ ở call site

Dùng khi overload thực sự có nghĩa khác nhau và caller biết mình cần cái nào:

~~~java
handle((String) null);
handle((Integer) null);
~~~

Hoặc khai báo biến có kiểu cụ thể rồi truyền vào. Lưu ý `(String) null` **không đảm bảo** giải quyết nếu hai overload đều nhận các superinterface khác nhau của `String` (như `CharSequence` và `Serializable`). Khi đó cần cast tới đúng interface mong muốn hoặc sửa thiết kế.

### Giải pháp B — Dùng tên method thể hiện nghiệp vụ

~~~java
findByUsername(String username);
findByNumericId(Integer id);
~~~

Đây là **chữ ký API minh họa**, khác nhau rõ về vai trò dữ liệu. Với trường hợp `null`, caller vẫn cần chọn chính sách hợp lệ, nhưng tên method đã cho biết truy vấn muốn thực hiện. Cách này thường tốt hơn khi hai overload mang **hai hành vi khác nhau** chứ không đơn thuần là hai hình thức cùng dữ liệu.

### Giải pháp C — Một parameter object hoặc kiểu miền nghiệp vụ

~~~java
record SearchRequest(String query, Integer limit) {
    SearchRequest {
        if (query == null || query.isBlank()) {
            throw new IllegalArgumentException("query is required");
        }
        if (limit != null && limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }
    }
}
~~~

Đây là khai báo kiểu minh họa Java 17+. Method nhận `SearchRequest` có chữ ký rõ một đối tượng yêu cầu, và kiểu đó quy định `query` bắt buộc, `limit` tùy chọn. Nó không cần hai overload cùng tên `search(String)` và `search(Integer)`. Tuy nhiên, không nên gom hai hành vi hoàn toàn độc lập vào một request object chỉ để bớt lỗi mơ hồ; thiết kế vẫn phải phản ánh đúng domain.

### Không nên sửa bằng cách nào?

- Không tùy tiện xóa một overload public đã được dùng ở nơi khác mà chưa kiểm tra compatibility.
- Không cast null thành một kiểu ngẫu nhiên chỉ để compiler im lặng; phải xác định hành vi mong muốn và chính sách null.
- Không thêm overload `Object` với hy vọng Java sẽ tự rơi vào đó khi các overload chuyên biệt mơ hồ.
- Không đổi return type để cố “phân biệt” hai method cùng chữ ký.
- Không dựa vào thứ tự khai báo hoặc vào loại object runtime để chọn overload.

## 18. Quy trình chẩn đoán lỗi `reference to ... is ambiguous`

Khi gặp một lời gọi như `operation(null)` báo ambiguity, làm theo các bước:

1. **Liệt kê overload ứng viên** có cùng tên và hình thức gọi phù hợp, kể cả các method được kế thừa nếu có. Kiểm tra constructor overload nếu đang dùng `new`.
2. **Xác định kiểu compile time của từng argument**. Literal null khác với biến `Object value = null` và `String value = null`.
3. **Lọc method áp dụng** theo số lượng tham số và chuyển đổi cho phép. Primitive không trực tiếp nhận null; reference type có thể nhận.
4. **Xét quan hệ subtype giữa các kiểu tham số**. `String` cụ thể hơn `Object`; `String` và `Integer` không có quan hệ subtype; hai interface không có quan hệ kế thừa có thể cùng áp dụng.
5. **Xét varargs/boxing/generic khi cần**; đừng giả định cứ có một method nhận `Object` hoặc `Object...` là nó thắng.
6. **Chọn sửa call site hay API**. Cast chỉ khi mong muốn overload cụ thể; đổi tên method/parameter object nếu sự mơ hồ là vấn đề sử dụng lặp lại.
7. **Chạy kiểm thử null** sau khi code biên dịch, vì ambiguity được giải quyết không đồng nghĩa thân method xử lý null đúng.

Khi compiler báo những ứng viên xung đột, đọc cả **chữ ký của các method** trong thông báo. Đó là manh mối cho biết cặp overload nào không thể phân biệt bằng kiểu đối số hiện tại.

### Phân biệt ba loại lỗi liên quan null

| Tình huống | Lỗi hoặc kết quả |
| --- | --- |
| Chỉ có `f(int)`, gọi `f(null)` | Không có method applicable cho argument null; **không phải** ambiguity |
| Có `f(String)` và `f(Integer)`, gọi `f(null)` | Hai ứng viên không thể chọn cụ thể nhất: **ambiguous** |
| Đã chọn `f(String)`, truyền null và thân gọi `text.length()` | Biên dịch có thể thành công; **`NullPointerException` khi chạy** |

Cần giải quyết đúng loại lỗi. Nếu không có method áp dụng, hãy sửa kiểu hoặc giá trị đối số. Nếu ambiguous, làm rõ lựa chọn overload. Nếu `NullPointerException`, kiểm tra hợp đồng và xử lý null trong luồng chạy.

## 19. Tương thích API: thêm overload có thể làm mã cũ ngừng biên dịch

Giả sử phiên bản đầu chỉ có:

~~~java
static void submit(Object value) { /* ... */ }
static void submit(String value) { /* ... */ }
~~~

Lời gọi `submit(null)` chọn `submit(String)`. Sau này thư viện bổ sung:

~~~java
static void submit(Integer value) { /* ... */ }
~~~

Bây giờ **mã nguồn biên dịch lại** có `submit(null)` có thể gặp ambiguity giữa `String` và `Integer`. Đây là ví dụ về thay đổi **source compatibility**: một overload mới làm call site cũ thiếu tính xác định.

Phải phân biệt mã nguồn biên dịch lại và binary đã biên dịch từ trước. Class đã biên dịch thường lưu lời gọi tới descriptor của overload đã chọn; việc **thêm** overload mới vào thư viện thường không khiến JVM tự chạy lại overload resolution cho bytecode cũ. Tuy nhiên thay đổi/xóa các chữ ký hay hành vi khác vẫn có thể gây vấn đề tương thích riêng, nên thư viện công khai cần đánh giá trước khi phát hành.

Các cách hạn chế rủi ro:

- Đặt tên khác nhau cho những hành vi nhận kiểu không liên quan.
- Bổ sung overload chỉ khi trường hợp sử dụng rõ và có test compile-time cho các call site quan trọng, đặc biệt null literal.
- Với API phát triển nhiều tuỳ chọn, dùng đối tượng yêu cầu hoặc builder có chính sách null nhất quán.
- Không xem overload chỉ là “thêm lựa chọn vô hại”: compiler phải chọn giữa **toàn bộ tập ứng viên** trong ngữ cảnh nguồn mới.

## 20. Bài thực hành dự đoán compiler

Trước khi đọc đáp án, hãy thử đánh dấu “biên dịch được và gọi overload nào” hoặc “không biên dịch”.

### Bài 1 — Quan hệ cha con

~~~java
static void call(Object value) {
    System.out.println("Object");
}

static void call(Number value) {
    System.out.println("Number");
}

static void call(Integer value) {
    System.out.println("Integer");
}
~~~

Với `call(null)`, kết quả là **Integer** vì `Integer` kế thừa `Number`, và `Number` kế thừa `Object`. Nếu truyền `Number n = null; call(n);`, compiler chọn **Number** vì kiểu khai báo đối số là `Number`.

### Bài 2 — Hai kiểu tham chiếu không liên quan

~~~java
static void call(String value) {
    System.out.println("String");
}

static void call(StringBuilder value) {
    System.out.println("StringBuilder");
}
~~~

`call(null)` **mơ hồ**. `call((String) null)` chọn **String**, `call((StringBuilder) null)` chọn **StringBuilder**. `String` và `StringBuilder` cùng có thể chứa văn bản nhưng không có quan hệ subtype trực tiếp giữa hai class này.

### Bài 3 — Primitive và wrapper

~~~java
static void call(long value) {
    System.out.println("long");
}

static void call(Integer value) {
    System.out.println("Integer");
}
~~~

`call(null)` chọn **Integer**; `long` không thể nhận null. `call(5)` chọn **long** vì phương thức `long` áp dụng thông qua widening primitive ở giai đoạn ưu tiên trước boxing `int → Integer`.

### Bài 4 — Interface chồng lấp

~~~java
static void call(CharSequence value) {
    System.out.println("CharSequence");
}

static void call(java.io.Serializable value) {
    System.out.println("Serializable");
}
~~~

`call("Java")` mơ hồ, vì `String` triển khai cả hai interface. `call((String) null)` vẫn mơ hồ. `call((CharSequence) null)` chọn **CharSequence** và `call((java.io.Serializable) null)` chọn **Serializable**.

### Bài 5 — Kiểu tham chiếu compile time

~~~java
static void call(Object value) {
    System.out.println("Object");
}

static void call(String value) {
    System.out.println("String");
}
~~~

Trong method:

~~~java
Object a = "Java";
String b = null;
call(a);
call(b);
~~~

Kết quả là:

~~~text
Object
String
~~~

Runtime object của `a` là String, nhưng overload vẫn chọn theo **kiểu khai báo Object** của argument.

Các bài 1–5 cung cấp các **đoạn method minh họa**, không phải một chương trình độc lập khi đặt tất cả trong cùng file, vì trùng tên và chữ ký giữa các bài. Hãy kiểm tra từng bài trong class riêng khi thực hành.

## 21. Bài tập ứng dụng và tiêu chí tự đánh giá

**Bài A — Chẩn đoán compiler:** Tạo class có `parse(String)`, `parse(Integer)`, viết `parse(null)` và chạy `javac` để đọc lỗi. Tiếp đó sửa bằng cast kiểu chính xác, nhưng giữ method kiểm tra null rõ ràng.

**Bài B — Thêm overload vào API:** Bắt đầu với `send(Object)` và `send(String)`; kiểm tra `send(null)`. Thêm `send(Integer)` rồi thử biên dịch lại. Giải thích vì sao `send(null)` trước đây có thể compile nhưng nay ambiguous.

**Bài C — Interface:** Tạo overload `format(CharSequence)` và `format(Serializable)`. Dự đoán kết quả đối với `format("x")`, `format((CharSequence) null)` và `format((String) null)`. Giải thích vì sao cast String không đủ.

**Bài D — Varargs:** Với `show(String... values)`, thử `show((String[]) null)`, `show((String) null)`, `show(new String[] {null})` và `show()`; in cả trạng thái `values == null` và độ dài khi không null. Đừng gọi `values.length` trước khi kiểm tra null.

**Bài E — Thiết kế lại API:** Thay hai overload `find(String code)`, `find(Integer id)` bằng `findByCode(String code)` và `findById(int id)`, hoặc mô hình có kiểu ID riêng. Viết các trường hợp kiểm thử để bảo đảm null không bị hiểu là một định danh hợp lệ.

Checklist cuối bài:

- [ ] Tôi giải thích được null literal dùng được với reference type và không trực tiếp dùng được với primitive type.
- [ ] Tôi biết compiler chọn `f(String)` thay `f(Object)` cho `f(null)` khi chỉ có hai overload đó.
- [ ] Tôi biết `f(String)` và `f(Integer)` làm `f(null)` mơ hồ.
- [ ] Tôi phân biệt kiểu compile time của biến `Object o = null` với literal `null`.
- [ ] Tôi biết cast có thể giải quyết ambiguity, nhưng cast sang `String` vẫn không đủ khi hai overload nhận `CharSequence` và `Serializable`.
- [ ] Tôi phân biệt mảng null, mảng rỗng và mảng chứa phần tử null trong varargs.
- [ ] Tôi biết một overload primitive `int` không nhận null, còn `Integer` nhận được.
- [ ] Tôi phân biệt lỗi compile-time ambiguity và runtime `NullPointerException`.
- [ ] Tôi biết thêm overload mới có thể làm một lời gọi null cũ không còn biên dịch được.
- [ ] Tôi biết khi nào nên đổi tên method, dùng domain type hoặc parameter object để tránh caller phải cast null.

**Điều cốt lõi:** Lời gọi chứa `null` không tạo ra “phiên bản mặc định” của phương thức. Java chọn overload bằng các quy tắc **áp dụng được và cụ thể nhất ở compile time**. Khi nhiều tham số là các kiểu tham chiếu không so sánh được về độ cụ thể, compiler phải báo ambiguity để yêu cầu người lập trình làm rõ. Hiểu cơ chế này giúp bạn đọc lỗi chính xác và thiết kế những API Java ít bất ngờ hơn.
