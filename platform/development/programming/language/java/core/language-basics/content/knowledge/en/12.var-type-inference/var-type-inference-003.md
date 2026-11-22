# Những vị trí được phép dùng `var` trong Java 17+

> **Java core — language-basics / Suy luận với var**  
> **Yêu cầu:** JDK 17+; ví dụ độc lập, không sử dụng thư viện ngoài Java.  
> **Mục tiêu:** Biết chính xác nơi được dùng `var`, nơi không được dùng, vì sao trình biên dịch suy ra kiểu tại thời điểm biên dịch và cách chọn `var` mà không làm mã khó đọc.

## 1. `var` là suy luận kiểu cục bộ, không phải kiểu động

Từ **Java 10**, Java cho phép viết `var` ở một số khai báo biến cục bộ thay cho tên kiểu tường minh:

~~~java
var count = 3;          // Trình biên dịch suy ra int.
var title = "Java";     // Suy ra String.
var price = 12.5;       // Suy ra double.
~~~

Kiểu được **suy ra khi biên dịch** từ biểu thức khởi tạo (hoặc từ ngữ cảnh hợp lệ của vòng lặp/lambda), sau đó **cố định**. Không thể gán một kiểu tùy ý khác vào cùng biến:

~~~java
var count = 3;
// count = "three"; // Lỗi biên dịch: count có kiểu int, không phải String.
~~~

`var` **không phải** tên một kiểu dữ liệu thực, không phải `Object` mặc định và không mang cơ chế “dynamic typing”. Java không cho dùng `var` ở mọi nơi có thể viết một tên kiểu.

## 2. Danh sách vị trí được phép

| Vị trí | Ví dụ hợp lệ | Kiểu được xác định như thế nào? |
| --- | --- | --- |
| Biến cục bộ có khởi tạo trong phương thức | `var number = 42;` | Theo biểu thức `42` → `int` |
| Biến cục bộ trong constructor hoặc khối khởi tạo | `var text = "ok";` | Theo biểu thức khởi tạo → `String` |
| Phần khai báo khởi tạo của `for` thông thường | `for (var i = 0; i < 3; i++)` | Theo `0` → `int` |
| Biến phần tử trong enhanced `for` | `for (var item : names)` | Theo kiểu phần tử của mảng/`Iterable` |
| Biến tài nguyên trong `try-with-resources` | `try (var reader = new StringReader("hi"))` | Theo đối tượng tài nguyên được khởi tạo |
| Tham số **lambda** có `var` | `(var a, var b) -> a + b` | Theo *target functional interface* của lambda; hỗ trợ từ **Java 11** |

Đối với biến cục bộ thông thường, **phải có initializer**. Enhanced `for` suy ra kiểu từ phần tử được duyệt; lambda suy ra từ kiểu mục tiêu (ví dụ `BiFunction<Integer, Integer, Integer>`). Đây là các dạng cú pháp hợp lệ riêng, không phải “cho phép biến `var` bất kỳ ở mọi nơi”.

### Biến cục bộ trong block

~~~java
void print() {
    var message = "Hello"; // String cục bộ.
    {
        var active = true;  // boolean cục bộ trong block lồng.
        System.out.println(message + active);
    }
}
~~~

Tương tự, trong **thân constructor**, khối `static { ... }` hoặc khối khởi tạo instance `{ ... }`, có thể dùng `var` để khai báo **biến cục bộ** thuộc block. Nhưng **field** của class vẫn phải khai báo bằng kiểu cụ thể.

## 3. `var` trong hai kiểu vòng lặp `for`

### `for` thông thường

~~~java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

`i` được suy ra `int` từ `0` và chỉ có phạm vi phù hợp với cấu trúc vòng lặp. Không có chuyện `i` tự đổi kiểu khi giá trị tăng.

### Enhanced `for` trên mảng hoặc collection

~~~java
String[] fruits = {"cam", "tao"};
for (var fruit : fruits) {
    System.out.println(fruit); // fruit có kiểu String.
}
~~~

Cũng có thể dùng `for (var element : list)` với collection có kiểu phần tử cụ thể. **`var` không tự khám phá kiểu runtime của từng object**: compiler suy ra kiểu phần tử tĩnh từ khai báo mảng hoặc kiểu phần tử được khai báo của `Iterable`.

Nếu collection được khai báo `List<Object>` thì `var element` được suy ra `Object`, dù vài phần tử thực tế là `String`. Do đó lựa chọn kiểu generic của collection vẫn rất quan trọng.

## 4. `var` trong `try-with-resources`

Một biến tài nguyên trong `try-with-resources` có thể khai báo bằng `var` nếu biểu thức khởi tạo có kiểu tài nguyên hợp lệ (triển khai `AutoCloseable`):

~~~java
import java.io.StringReader;

try (var reader = new StringReader("AB")) {
    System.out.println((char) reader.read()); // A
}
~~~

`reader` được suy ra `StringReader`, có phương thức `read()`. Khi rời khối `try`, `close()` được gọi tự động theo cơ chế `try-with-resources`.

**Đừng nhầm** `var` với quy tắc của tài nguyên: chỉ những object có kiểu phù hợp `AutoCloseable` mới được khai báo làm resource. `try (var number = 10) { ... }` **không hợp lệ** vì `int` không phải tài nguyên có thể đóng.

## 5. `var` trong tham số lambda — Java 11 trở lên

Khi lambda có **target type** rõ ràng, từ Java 11 có thể dùng `var` cho **tất cả** tham số:

~~~java
import java.util.function.BiFunction;

BiFunction<Integer, Integer, Integer> add =
        (var left, var right) -> left + right;
System.out.println(add.apply(4, 5)); // 9
~~~

Ở đây compiler biết lambda phải triển khai `BiFunction<Integer, Integer, Integer>` nên `left` và `right` tương ứng có kiểu `Integer` (và phép `+` tự unbox để cộng). `var` không làm suy luận kiểu lambda từ hư không: lambda **vẫn cần kiểu đích**.

Cách dùng hợp lệ đối với hai tham số:

~~~java
BiFunction<Integer, Integer, Integer> a = (x, y) -> x + y;
BiFunction<Integer, Integer, Integer> b = (var x, var y) -> x + y;
BiFunction<Integer, Integer, Integer> c =
        (Integer x, Integer y) -> x + y;
~~~

**Không trộn kiểu khai báo của các tham số cùng lambda:**

~~~java
// KHÔNG biên dịch:
// BiFunction<Integer, Integer, Integer> bad = (var x, y) -> x + y;
// BiFunction<Integer, Integer, Integer> bad2 = (var x, Integer y) -> x + y;
~~~

Nếu dùng `var` cho một tham số lambda thì các tham số còn lại cũng phải dùng `var`. Dạng `var` tiện khi cần dùng annotation hợp lệ trên tham số mà vẫn muốn kiểu được suy luận, nhưng trong ví dụ cơ bản có thể chọn cú pháp `(x, y) -> ...` đơn giản hơn.

## 6. Những vị trí **không** được phép dùng `var`

| Vị trí hoặc kiểu khai báo | Ví dụ không hợp lệ | Lý do |
| --- | --- | --- |
| Field của class (kể cả `static`) | `class A { var n = 1; }` | `var` chỉ được hỗ trợ trong ngữ cảnh cục bộ cho phép |
| Kiểu trả về của method | `var getCount() { return 1; }` | Return type phải khai báo rõ |
| Tham số phương thức thường | `void send(var message) { }` | Không phải lambda formal parameter |
| Tham số constructor | `A(var value) { }` | Không dùng `var` tại khai báo tham số constructor |
| Tham số `catch` | `catch (var ex) { }` | Cần kiểu exception |
| Biến cục bộ không khởi tạo | `var n;` | Không có thông tin để suy ra kiểu |
| Khởi tạo chỉ bằng `null` | `var value = null;` | `null` không đủ suy ra một kiểu |
| Khai báo nhiều biến trong một câu | `var a = 1, b = 2;` | Khai báo dùng `var` chỉ được một biến |
| Array initializer không có `new` | `var data = {1, 2};` | Không có kiểu mục tiêu cho initializer này |
| Tự tham chiếu trong initializer | `var n = n + 1;` | Không thể suy ra kiểu hợp lệ từ chính biến đang khai báo |

**Cách sửa:**

~~~java
int n;                         // Không cần initializer ở đây.
String value = null;           // Kiểu tường minh nếu muốn null ban đầu.
var typedNull = (String) null; // Hợp lệ: kiểu String đến từ cast.
var data = new int[] {1, 2};  // Hợp lệ: kiểu suy ra int[].
var a = 1;                     // Mỗi khai báo var một biến.
var b = 2;
~~~

Trường hợp `var typedNull = (String) null;` hợp lệ về **cú pháp suy luận kiểu**, nhưng trong ứng dụng thật cần xem liệu null có ý nghĩa không. Đừng cast chỉ để tránh một khai báo kiểu rõ ràng.

## 7. Ví dụ Java 17+ runnable

Tạo file **VarAllowedPlacesDemo.java** chứa nguyên chương trình:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.function.BiFunction;

public final class VarAllowedPlacesDemo {
    public static void main(String[] args) throws IOException {
        var language = "Java";
        var count = 2;
        var names = new ArrayList<String>();
        names.add("An");
        names.add("Binh");

        System.out.println("local=" + language + ":" + count);

        for (var index = 0; index < names.size(); index++) {
            System.out.println("index=" + index + ":" + names.get(index));
        }

        for (var name : names) {
            System.out.println("each=" + name);
        }

        try (var reader = new StringReader("OK")) {
            var first = (char) reader.read();
            var second = (char) reader.read();
            System.out.println("resource=" + first + second);
        }

        BiFunction<Integer, Integer, Integer> plus =
                (var left, var right) -> left + right;
        System.out.println("lambda=" + plus.apply(4, 5));

        var scores = new int[] {3, 7};
        System.out.println("array=" + (scores[0] + scores[1]));

        var typedNull = (String) null;
        System.out.println("typedNull=" + (typedNull == null));
    }
}
~~~

Mở terminal tại thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt) rồi chạy:

~~~bash
javac -encoding UTF-8 VarAllowedPlacesDemo.java
java VarAllowedPlacesDemo
~~~

**Expected output chính xác:**

~~~text
local=Java:2
index=0:An
index=1:Binh
each=An
each=Binh
resource=OK
lambda=9
array=10
typedNull=true
~~~

Những vị trí `var` đã minh họa:

1. `language`, `count`, `names`, `scores` và `typedNull` là **biến cục bộ có initializer**.
2. `index` được khai báo trong phần khởi tạo của vòng `for` thường.
3. `name` là biến phần tử của enhanced `for`, suy ra `String` từ `ArrayList<String>`.
4. `reader` là tài nguyên `try-with-resources`, suy ra `StringReader`.
5. `left` và `right` là tham số lambda (hợp lệ từ Java 11).
6. Giá trị `typedNull` bằng null nhưng **kiểu suy luận là String** do có cast; đối lập với `var typedNull = null;` không hợp lệ.

## 8. Khi nào nên dùng `var` để code dễ hiểu?

`var` giảm lặp kiểu, nhưng không bắt buộc. Hãy dùng khi **kiểu rõ từ initializer** hoặc ngữ cảnh:

~~~java
var reader = new StringReader("Hi"); // Kiểu StringReader rõ.
var count = 0;                        // Kiểu int rõ.
~~~

Cân nhắc kiểu tường minh khi initializer không nói rõ ý nghĩa hoặc dễ suy luận nhầm:

~~~java
var result = calculate();       // Muốn hiểu result phải biết calculate() trả gì.
double result2 = calculate();   // Thể hiện ngay kiểu kỳ vọng.
~~~

Lưu ý đặc biệt với generic diamond:

~~~java
var list = new ArrayList<>();        // Thường suy ra ArrayList<Object>.
var strings = new ArrayList<String>(); // Kiểu phần tử String rõ ràng.
~~~

Nếu cần kiểu API là `List<String>` thay vì concrete class `ArrayList<String>`, có thể viết `List<String> names = new ArrayList<>();`. `var` không tự chọn abstraction cho bạn.

**`var` không thay thế phân tích kiểu**: vẫn cần xem literal số là `int`/`long`/`double`, kiểu generic của initializer, và các phép chuyển kiểu Java có thể thực hiện.

## 9. Bài tập tự kiểm tra

**Bài 1.** Đánh dấu hợp lệ/không hợp lệ: `var x = 1;`, `var y;`, `var z = null;`, `var a = new int[]{2, 3};`, `var b = {2, 3};`.

**Bài 2.** Chuyển vòng `for (int i = 0; i < 5; i++)` sang `var`. Kiểu suy ra là gì? Khi nào biến rời phạm vi?

**Bài 3.** Cho `ArrayList<String>` có hai phần tử; viết enhanced `for` dùng `var` để in từng phần tử. Kiểu tĩnh của biến phần tử là gì?

**Bài 4.** Dùng `try (var reader = new StringReader("A"))` để đọc ký tự. Vì sao kiểu tài nguyên phải triển khai `AutoCloseable`?

**Bài 5.** Khai báo một `BiFunction<Integer, Integer, Integer>` bằng lambda sử dụng hai tham số `var`. Sau đó thử sửa một tham số thành `Integer` và giải thích lỗi biên dịch.

### Ghi nhớ

`var` được dùng ở **biến cục bộ có initializer**, **phần khai báo của `for`**, **biến enhanced `for`**, **biến tài nguyên `try-with-resources`**, và **tham số lambda** (từ Java 11). `var` **không** được dùng làm kiểu của field, return type, tham số method/constructor, tham số `catch` hoặc biến cục bộ thiếu dữ liệu suy luận. Kiểu vẫn được chốt tại **compile time**; hãy ưu tiên sự rõ ràng của mã nguồn.
