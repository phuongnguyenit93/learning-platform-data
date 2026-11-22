# `var` trong Java: Kiểu được xác định tại thời điểm biên dịch

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích vì sao `var` (local variable type inference, được giới thiệu từ Java 10) **vẫn là cơ chế kiểm tra kiểu tĩnh**, dự đoán kiểu của biến từ biểu thức khởi tạo, phân biệt kiểu tĩnh của biến với lớp thực tế của đối tượng khi chạy, và nhận biết những trường hợp suy luận kiểu gây lỗi hoặc không phù hợp.

## 1. Trình biên dịch xác định kiểu của `var` như thế nào?

Với khai báo biến cục bộ dạng `var tenBien = bieuThuc;`, trình biên dịch Java phân tích **kiểu của biểu thức bên phải** ngay trong quá trình biên dịch rồi dùng kiểu đó làm **kiểu tĩnh của biến**. Sau thời điểm này, mọi phép gán, lời gọi phương thức và phép toán với biến đều được kiểm tra theo kiểu đã suy luận, giống như khi bạn ghi kiểu tường minh.

~~~java
var soLuong = 10;       // Kiểu suy luận: int
var ten = "Java";       // Kiểu suy luận: String
var tyLe = 1.5;         // Kiểu suy luận: double

soLuong = 20;           // Hợp lệ: int -> int
ten = "Java 17";        // Hợp lệ: String -> String
// soLuong = "hai mươi"; // Lỗi biên dịch: không gán String cho int
~~~

Ba điểm cần nhớ:

1. `var` **không phải kiểu dữ liệu động** và không làm biến tự đổi kiểu khi có phép gán mới.
2. `var` **không mặc định là Object**. Kiểu suy luận có thể là kiểu nguyên thủy (`int`, `double`, ...), lớp, interface, mảng hoặc kiểu có tham số generic.
3. **Kiểu tĩnh được chốt lúc biên dịch**. Giá trị và đối tượng mà biến tham chiếu có thể thay đổi khi chương trình chạy, nhưng mọi phép sử dụng biến vẫn phải tương thích với kiểu tĩnh đó.

Ví dụ đầu tiên ở trên chỉ là đoạn mã đặt bên trong phương thức; phần sau có chương trình đầy đủ để biên dịch và chạy.

## 2. Ví dụ Java 17+ có thể chạy

Lưu toàn bộ mã sau vào file **VarCompileTimeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarCompileTimeDemo {
    public static void main(String[] args) {
        var count = 10;                       // int
        count += 5;

        var title = "Java";                   // String
        var names = new ArrayList<String>(); // ArrayList<String>
        names.add("An");
        names.add("Bình");

        List<String> view = names;
        var first = view.get(0);              // String, vì view là List<String>

        System.out.println(count);
        System.out.println(title.toUpperCase());
        System.out.println(first);
        System.out.println(names.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac VarCompileTimeDemo.java
java VarCompileTimeDemo
~~~

Kết quả chính xác:

~~~text
15
JAVA
An
2
~~~

Giải thích:

- Biểu thức `10` có kiểu `int`, vì vậy `count` là `int`; phép cộng gán giữ phép kiểm tra kiểu của `int`.
- Chuỗi `"Java"` có kiểu `String`; trình biên dịch biết `title.toUpperCase()` tồn tại.
- Biểu thức `new ArrayList<String>()` có kiểu `ArrayList<String>`; `var` giữ kiểu cụ thể này, bao gồm thông tin generic.
- `view` được khai báo là `List<String>`, nên `view.get(0)` trả về `String` theo kiểu tĩnh của API, và `first` cũng được suy luận là `String`.

Thay `var count = 10;` bằng `int count = 10;` không làm biến trở nên "tĩnh hơn": cả hai đều được kiểm tra kiểu ngay lúc biên dịch. `var` chỉ giúp bỏ phần tên kiểu bị lặp khi kiểu đã rõ từ biểu thức.

## 3. Kiểu tĩnh khác lớp của đối tượng lúc chạy

Java có tính đa hình: biến có kiểu tĩnh rộng hơn lớp của đối tượng được tham chiếu. `var` suy luận từ **kiểu tĩnh của biểu thức khởi tạo**, không dò đối tượng thực tế để đoán kiểu cụ thể hơn.

Lưu ví dụ độc lập vào file **StaticVsRuntimeDemo.java**:

~~~java
public class StaticVsRuntimeDemo {
    public static void main(String[] args) {
        Object source = "Java";

        var fromObject = source;           // Kiểu tĩnh: Object
        var fromCast = (String) source;    // Kiểu tĩnh: String

        System.out.println(fromObject.getClass().getSimpleName());
        System.out.println(fromCast.toUpperCase());
    }
}
~~~

~~~bash
javac StaticVsRuntimeDemo.java
java StaticVsRuntimeDemo
~~~

~~~text
String
JAVA
~~~

Mặc dù `fromObject.getClass()` cho thấy đối tượng hiện tại là `String`, lời gọi `fromObject.toUpperCase()` **không biên dịch**, vì phương thức này không được khai báo trên kiểu tĩnh `Object`. Ngược lại, phép ép kiểu `(String) source` làm biểu thức khởi tạo có kiểu `String`, nên `fromCast.toUpperCase()` hợp lệ. Việc ép kiểu chỉ an toàn khi đối tượng thực sự tương thích; nếu không, Java có thể ném `ClassCastException` lúc chạy.

Vì vậy, hãy phân biệt hai câu hỏi: **"Trình biên dịch cho phép gọi phương thức nào?"** (dựa vào kiểu tĩnh) và **"Đối tượng đang thuộc lớp nào?"** (kiểm tra lúc chạy). `var` chỉ tham gia câu hỏi thứ nhất.

## 4. Nhìn biểu thức khởi tạo để dự đoán kiểu

| Khai báo | Kiểu tĩnh được suy luận | Lưu ý |
| --- | --- | --- |
| `var n = 10;` | `int` | Literal số nguyên mặc định là `int` khi giá trị phù hợp. |
| `var n = 10L;` | `long` | Hậu tố `L` quyết định literal có kiểu `long`. |
| `var p = 2.5;` | `double` | Literal thập phân mặc định là `double`. |
| `var p = 2.5f;` | `float` | Hậu tố `f` tạo `float`. |
| `var s = "Hello";` | `String` | Không phải `Object`. |
| `var a = new int[]{1, 2};` | `int[]` | Biểu thức tạo mảng có kiểu rõ ràng. |
| `var x = new ArrayList<String>();` | `ArrayList<String>` | Giữ kiểu cụ thể và đối số generic. |
| `var x = List.of("An", "Bình");` | `List<String>` | Kiểu trả về của phương thức generic được suy luận từ đối số. |

Hai ví dụ cho thấy **suy luận kiểu không thay đổi quy tắc tính toán của Java**:

~~~java
var a = 7 / 2;     // int, giá trị 3: chia số nguyên
var b = 7.0 / 2;   // double, giá trị 3.5
~~~

Trình biên dịch cũng dùng các quy tắc suy luận generic thông thường. Chẳng hạn:

~~~java
var list1 = new ArrayList<>();          // ArrayList<Object>
List<String> list2 = new ArrayList<>(); // List<String>
~~~

Ở `list1`, không có kiểu đích `List<String>` để hướng dẫn toán tử diamond `<>`, nên phần tử được suy luận là `Object`; thêm cả `String` lẫn `Integer` sẽ được chấp nhận. Ở `list2`, khai báo tường minh tạo ngữ cảnh generic và chặn phần tử sai kiểu ngay khi biên dịch. **Đừng mặc định `var` sẽ suy ra kiểu phần tử mà bạn mong muốn nếu biểu thức khởi tạo không mang đủ thông tin.**

## 5. Những trường hợp không thể suy luận kiểu hợp lệ

`var` cần một biểu thức khởi tạo có đủ thông tin kiểu. Các đoạn dưới đây **cố ý minh họa lỗi biên dịch** (không ghép trực tiếp vào chương trình chạy ở mục 2):

~~~java
var x;                 // Lỗi: không có biểu thức khởi tạo
var y = null;          // Lỗi: không suy luận được kiểu chỉ từ null
var a = 1, b = 2;      // Lỗi: không khai báo nhiều biến bằng var trong một khai báo
var numbers = {1, 2};  // Lỗi: array initializer không có kiểu đích
~~~

Cách viết hợp lệ khi cần thiết:

~~~java
String y = null;
var numbers = new int[]{1, 2};
~~~

Lambda và method reference cũng cần một **kiểu hàm đích** để xác định cách gọi; ví dụ sau không thể dùng `var` trực tiếp cho biểu thức lambda:

~~~java
// var doubleIt = n -> n * 2;  // Lỗi: lambda không có kiểu đích
java.util.function.IntUnaryOperator doubleIt = n -> n * 2;
~~~

Trong Java hiện đại, `var` dùng cho **biến cục bộ** có thể suy luận kiểu, kể cả biến trong vòng `for`, biến của vòng `for-each` và tài nguyên khai báo trong `try-with-resources` khi đúng cú pháp. `var` không dùng làm kiểu của field, kiểu trả về phương thức hay tham số phương thức thông thường. Từ Java 11, cú pháp `var` còn được hỗ trợ cho **tham số lambda được khai báo tường minh**; đây là cú pháp khác với việc suy luận kiểu từ một biểu thức khởi tạo biến cục bộ.

## 6. Khi nào dùng `var`, khi nào ghi kiểu tường minh?

Nên cân nhắc `var` nếu biểu thức bên phải cho người đọc thấy rõ kiểu và biến có phạm vi ngắn:

~~~java
var names = new ArrayList<String>();
var total = invoiceCount + pendingCount; // Phù hợp nếu toán hạng có kiểu rõ trong ngữ cảnh
~~~

Ưu tiên kiểu tường minh khi **kiểu là một phần chủ đích thiết kế**, chẳng hạn muốn phụ thuộc vào interface thay vì một lớp cài đặt cụ thể:

~~~java
List<String> names = new ArrayList<>();
~~~

Ở đây, biến có kiểu tĩnh `List<String>`. Nếu viết `var names = new ArrayList<String>();`, kiểu tĩnh sẽ là `ArrayList<String>`; code ở các dòng sau có thể vô tình dựa vào phương thức chỉ lớp cụ thể đó mới có. Chọn cú pháp theo điều mà người bảo trì cần hiểu, không chỉ theo số ký tự gõ được.

Cũng nên viết kiểu hoặc literal rõ ràng khi dễ nhầm `int`/`long`, `float`/`double`, hay kiểu phần tử generic. `var` không làm phép chuyển kiểu nguy hiểm trở nên hợp lệ và không thay thế thiết kế API: kiểu tham số, kiểu trả về và hợp đồng công khai vẫn cần khai báo rõ ràng.

## 7. Tự kiểm tra hiểu bài

Cho các dòng sau, hãy xác định kiểu tại thời điểm biên dịch và dòng nào báo lỗi:

~~~java
var id = 100;
var label = "item";
var value = (Object) label;

id = 101;
// id = 101L;
// value.toUpperCase();
~~~

Đáp án: `id` có kiểu `int`, `label` có kiểu `String`, còn `value` có kiểu `Object` do biểu thức ép kiểu. `id = 101` hợp lệ; `id = 101L` sẽ báo lỗi vì không thể tự động gán giá trị `long` cho biến `int` theo cách đó. `value.toUpperCase()` cũng báo lỗi vì kiểu `Object` không khai báo phương thức ấy, dù đối tượng bên trong có thể là `String`.

**Kết luận:** Trong Java 10 trở lên, `var` là cách để trình biên dịch **suy luận kiểu tĩnh một lần tại khai báo biến cục bộ**. Nó giúp giảm lặp tên kiểu, nhưng vẫn giữ nguyên cơ chế kiểm tra kiểu của Java trong suốt quá trình biên dịch và thực thi.
