# Giới hạn nhiều biến trong cùng một khai báo `var` (Java 10+)

## 1. Quy tắc cốt lõi

Trong Java, khi dùng `var` để **suy luận kiểu của biến cục bộ từ biểu thức khởi tạo**, mỗi **khai báo** chỉ được giới thiệu **một biến**. Không được dùng dấu phẩy để khai báo nhiều biến trong cùng một câu lệnh `var`, ngay cả khi tất cả có cùng kiểu giá trị.

~~~java
var first = 1;                 // Hợp lệ: một biến và có giá trị khởi tạo
var second = 2;                // Hợp lệ: một khai báo riêng

// KHÔNG hợp lệ: các ví dụ dưới đây không biên dịch.
// var a = 1, b = 2;
// var name = "Java", year = 10;
// final var min = 1, max = 5;
~~~

Ở đây **khai báo (declaration)** là một cấu trúc khai báo biến, còn **biểu thức khởi tạo (initializer)** là giá trị bên phải dấu `=`. Ví dụ `var a = 1, b = 2;` có hai *variable declarators* (`a = 1` và `b = 2`), nên không hợp lệ. Việc hai giá trị đều là `int` **không** tạo ra ngoại lệ.

Quy tắc này bắt đầu từ Java 10 và **vẫn được Java Language Specification duy trì trong các phiên bản Java hiện đại**. Đây là lỗi biên dịch, không phải lỗi lúc chạy; thông báo thường gặp là:

~~~text
'var' is not allowed in a compound declaration
~~~

Hạn chế nằm ở **số biến trong cùng một khai báo dùng `var`**, không phải tổng số biến được phép tạo trong phương thức, trong một khối lệnh, hay trong một dòng văn bản. Viết hai khai báo tách bằng dấu `;` là hợp lệ, dù có đặt chúng trên cùng dòng (không khuyến khích vì khó đọc).

## 2. So sánh với khai báo kiểu tường minh

Khai báo bằng **kiểu tường minh** vẫn có thể dùng dấu phẩy để khai báo nhiều biến cùng kiểu:

~~~java
int left = 1, right = 2;           // Hợp lệ: cùng kiểu int
String firstName = "An", lastName = "Nguyen"; // Hợp lệ: cùng kiểu String
~~~

Ở dạng này, kiểu viết ở đầu khai báo áp dụng cho tất cả biến được khai báo. Ví dụ `int a = 1, b = 2;` thì cả `a` lẫn `b` đều là `int`.

Nếu muốn dùng `var`, phải **tách từng khai báo**:

~~~java
var left = 1;       // int
var right = 2;      // int

var firstName = "An";      // String
var attemptCount = 10;     // int
~~~

Cách tách này còn cho phép từng biến có kiểu suy luận khác nhau. `var` không phải kiểu động: sau khi suy luận, biến vẫn có kiểu tĩnh và được trình biên dịch kiểm tra như một khai báo thông thường.

| Mong muốn | Dạng hợp lệ | Dạng không hợp lệ |
| --- | --- | --- |
| Hai biến cùng kiểu `int` trong một khai báo | `int a = 1, b = 2;` | `var a = 1, b = 2;` |
| Hai biến suy luận kiểu độc lập | `var a = 1; var b = 2;` | `var a = 1, b = 2;` |
| Hai biến khác kiểu | `var a = 1; var b = "hi";` | `var a = 1, b = "hi";` |
| Hai biến `final` cục bộ | `final var a = 1; final var b = 2;` | `final var a = 1, b = 2;` |

`final` giới hạn việc **gán lại biến**, nhưng không gỡ bỏ quy tắc “một biến trong mỗi khai báo `var`”.

## 3. Trong vòng lặp `for` truyền thống

Phần khởi tạo của vòng `for` có thể chứa một khai báo biến cục bộ. Vì thế, hạn chế của `var` cũng áp dụng tại đây.

~~~java
// KHÔNG biên dịch: một khai báo var chứa hai biến.
// for (var i = 0, j = 5; i < j; i++, j--) {
//     System.out.println(i + ":" + j);
// }
~~~

Nếu hai biến có cùng kiểu, chọn kiểu tường minh:

~~~java
for (int i = 0, j = 5; i < j; i++, j--) {
    System.out.println(i + ":" + j);
}
~~~

Kết quả:

~~~text
0:5
1:4
2:3
~~~

Phần `int i = 0, j = 5` hợp lệ vì dùng kiểu tường minh `int`. Phần `i++, j--` **vẫn hợp lệ**: dấu phẩy ở đó phân tách **biểu thức cập nhật**, không tạo thêm biến trong khai báo `var`. Đây là hai vị trí cú pháp khác nhau.

Nếu muốn suy luận kiểu cho cả hai, khai báo riêng trước vòng lặp:

~~~java
var i = 0;
var j = 5;
for (; i < j; i++, j--) {
    System.out.println(i + ":" + j);
}
~~~

Lưu ý khác biệt phạm vi: khi khai báo `int i, j` ngay trong `for`, hai biến chỉ thuộc phạm vi vòng lặp; khi khai báo `var i` và `var j` ở ngoài, chúng còn tồn tại trong phạm vi khối bao quanh sau khi vòng lặp kết thúc.

Ở vòng `for-each`, mỗi khai báo biến lặp cũng có một biến; cú pháp này hợp lệ:

~~~java
for (var value : java.util.List.of(2, 4, 6)) {
    System.out.println(value);
}
~~~

Không có cú pháp `for (var key, value : entries)` để khai báo cùng lúc hai biến lặp. Nếu cần cả khóa lẫn giá trị của một `Map`, có thể lặp từng `Map.Entry<K, V>` rồi lấy `entry.getKey()` và `entry.getValue()`.

## 4. Phân biệt dấu phẩy trong khai báo với dấu phẩy trong biểu thức

**Không phải mọi dấu phẩy nằm bên phải `var` đều bị cấm.** Java chỉ cấm nhiều *declarators* trong **cùng một khai báo** có kiểu `var`.

~~~java
var numbers = java.util.List.of(1, 2, 3);     // Hợp lệ: một biến numbers
var point = new int[] {10, 20};               // Hợp lệ: một biến point
var pair = java.util.Map.entry("code", 200);   // Hợp lệ: một biến pair
~~~

Trong các ví dụ này, các dấu phẩy phân tách **đối số phương thức** hoặc **phần tử mảng** trong biểu thức khởi tạo. Chúng không khai báo thêm biến.

Ngược lại:

~~~java
// KHÔNG biên dịch vì dấu phẩy phân tách hai biến.
// var numbers = java.util.List.of(1, 2), other = java.util.List.of(3, 4);
~~~

Điểm cần kiểm tra khi đọc mã là: *Sau dấu phẩy, Java đang bắt đầu khai báo một tên biến thứ hai, hay chỉ tiếp tục biểu thức khởi tạo của cùng một biến?*

## 5. Chương trình chạy đầy đủ

Lưu thành tệp **`VarDeclarationLimitDemo.java`**:

~~~java
import java.util.List;

public class VarDeclarationLimitDemo {
    public static void main(String[] args) {
        var first = 1;
        var second = 2;
        var words = List.of("Java", "10");

        System.out.println("sum=" + (first + second));
        System.out.println("words=" + words);

        // Hai biến trong một khai báo dùng kiểu tường minh.
        for (int i = 0, j = 3; i < j; i++, j--) {
            System.out.println("pair=" + i + "," + j);
        }

        // Một biến lặp được suy luận kiểu.
        for (var word : words) {
            System.out.println("word=" + word);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (chương trình cũng dùng được từ Java 10):

~~~bash
javac VarDeclarationLimitDemo.java
java VarDeclarationLimitDemo
~~~

`stdout` chính xác:

~~~text
sum=3
words=[Java, 10]
pair=0,3
pair=1,2
word=Java
word=10
~~~

Tại sao không lỗi? `first`, `second` và `words` là ba khai báo `var` **riêng biệt**; `i` và `j` có kiểu tường minh `int` trong một khai báo `for`; `word` là một biến lặp đơn lẻ.

## 6. Sửa lỗi khi trình biên dịch báo khai báo `var` dạng ghép

Nếu gặp lỗi `'var' is not allowed in a compound declaration`, tìm câu lệnh đang khai báo nhiều tên biến dưới cùng một `var`. Chọn một trong hai cách sửa:

**Cách A — Giữ `var`, tách khai báo:** phù hợp khi mỗi biến cần suy luận kiểu độc lập.

~~~java
// Thay cho: var min = 1, max = 10;
var min = 1;
var max = 10;
~~~

**Cách B — Dùng kiểu tường minh, giữ khai báo ghép:** phù hợp khi các biến thực sự cùng kiểu và cách viết ghép vẫn dễ hiểu.

~~~java
int min = 1, max = 10;
~~~

Nếu cần ràng buộc không gán lại, có thể chọn `final var min = 1; final var max = 10;` hoặc `final int min = 1, max = 10;`. Cả hai tuân thủ quy tắc khai báo.

**Lỗi tư duy thường gặp:**

- “Hai biểu thức đều trả về `int` nên `var a = 1, b = 2;` phải chạy được.” Sai: giới hạn kiểm tra **số biến**, không kiểm tra chúng có cùng kiểu hay không.
- “Dấu phẩy nào cũng bị cấm khi dùng `var`.” Sai: `var list = List.of("a", "b");` hoàn toàn hợp lệ vì chỉ khai báo một biến.
- “Có thể đặt `var` ở mọi vị trí khai báo giống `int`.” Sai: `var` chủ yếu dành cho suy luận kiểu biến cục bộ tại những vị trí Java cho phép, ví dụ trong khối lệnh, phần khai báo `for` hoặc `for-each`.
- “`final var` là ngoại lệ cho phép nhiều biến.” Sai: `final` không thay đổi quy tắc này.

## 7. Câu hỏi tự kiểm tra

Xác định dòng nào hợp lệ và vì sao (mỗi dòng xét độc lập):

~~~java
// A
var x = 1, y = 2;

// B
int x = 1, y = 2;

// C
var list = List.of(1, 2);

// D
final var x = 1, y = 2;

// E
var x = 1; var y = 2;
~~~

**Đáp án:** A sai (hai biến trong một khai báo `var`); B đúng (`int` được khai báo ghép); C đúng nếu có `import java.util.List;` (chỉ có một biến, dấu phẩy thuộc danh sách đối số); D sai (thêm `final` không thay đổi giới hạn); E đúng (hai khai báo `var` tách bằng dấu `;`, dù nên xuống dòng để dễ đọc).

**Ghi nhớ:** Với `var`, **một khai báo = một biến có biểu thức khởi tạo**. Muốn khai báo nhiều biến, hãy tách thành nhiều câu lệnh `var` hoặc ghi kiểu tường minh nếu phù hợp.

### Tham khảo chính thức

- [Java Language Specification, `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4): quy định rõ lỗi biên dịch khi khai báo `var` có nhiều hơn một *VariableDeclarator*.
