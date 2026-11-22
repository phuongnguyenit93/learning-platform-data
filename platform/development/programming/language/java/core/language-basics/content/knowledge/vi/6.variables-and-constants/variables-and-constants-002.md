# Kiểu khai báo quyết định giá trị biến có thể giữ

> **Java core — language-basics / Biến và hằng**  
> **Môi trường:** JDK 17 trở lên.  
> **Mục tiêu:** Hiểu kiểu khai báo ràng buộc giá trị có thể gán cho biến; phân biệt biến kiểu nguyên thủy và tham chiếu, phép chuyển kiểu, suy luận kiểu với `var` và quy tắc gán lại với `final`.

## 1. Biến có kiểu ngay từ lúc khai báo

Java là ngôn ngữ **kiểm tra kiểu tĩnh** (*statically typed*). Khi khai báo:

~~~java
int age = 20;
String name = "Lan";
boolean active = true;
~~~

compiler biết `age` có kiểu `int`, `name` có kiểu `String`, `active` có kiểu `boolean`. Một lần gán sau đó phải **tương thích với kiểu đã khai báo**, chứ không được tự do biến `age` thành biến chứa chuỗi.

Cấu trúc cơ bản: `Type variableName = initialValue;`. Ví dụ `int count = 3;` gồm kiểu `int`, tên `count` và biểu thức khởi tạo `3`. Biến cục bộ có thể khai báo trước rồi gán sau, nhưng phải được **gán chắc chắn trước khi đọc**:

~~~java
int count;
count = 3;
System.out.println(count); // 3
~~~

Điều này khác với field của object có giá trị mặc định khi object được tạo; đừng suy ra biến cục bộ chưa gán mặc nhiên bằng 0.

## 2. Kiểu nguyên thủy (*primitive*): giữ giá trị thuộc miền của kiểu

Java có tám kiểu nguyên thủy. Biến primitive giữ **giá trị** thuộc loại đó, không phải tham chiếu đến một object:

| Kiểu | Giá trị có thể giữ | Ví dụ |
| --- | --- | --- |
| `byte` | Số nguyên -128 đến 127 (8 bit) | `byte level = 100;` |
| `short` | Số nguyên -32768 đến 32767 (16 bit) | `short pages = 500;` |
| `int` | Số nguyên -2147483648 đến 2147483647 (32 bit) | `int amount = 10_000;` |
| `long` | Số nguyên có dấu 64 bit | `long total = 3_000_000_000L;` |
| `float` | Số thực dấu chấm động IEEE 754 32 bit, độ chính xác hữu hạn | `float rate = 1.5f;` |
| `double` | Số thực dấu chấm động IEEE 754 64 bit, độ chính xác hữu hạn | `double ratio = 1.5;` |
| `char` | Một đơn vị mã UTF-16, từ `'\u0000'` đến `'\uffff'` | `char grade = 'A';` |
| `boolean` | Chỉ `true` hoặc `false` | `boolean ready = true;` |

`char` không bảo đảm chứa trọn mọi ký tự Unicode: một số code point ngoài BMP cần **hai** đơn vị UTF-16. `float` và `double` có cả giá trị đặc biệt như NaN, vô cực; chúng không phải kiểu số thập phân chính xác cho mọi phép tính tiền tệ.

Với integer literal thập phân vượt phạm vi `int`, thêm hậu tố `L` để tạo literal `long`:

~~~java
long visitors = 3_000_000_000L;  // Đúng.
// long wrong = 3_000_000_000;  // Sai: literal mặc định int quá lớn.
~~~

`boolean` không tự chuyển thành số `0`/`1`; `int flag = true;` là lỗi kiểu.

## 3. Kiểu tham chiếu: kiểu khai báo giới hạn đối tượng được trỏ tới

`String`, array, class, interface, record… là **kiểu tham chiếu**. Biến tham chiếu giữ một **reference** tới object tương thích (hoặc `null`), không trực tiếp chứa toàn bộ object như biến primitive chứa một số.

~~~java
String title = "Java";
CharSequence text = title;           // String triển khai CharSequence.
Number number = Integer.valueOf(42); // Integer là Number.
number = Double.valueOf(2.5);       // Double cũng là Number.
Object item = "book";
item = Integer.valueOf(7);          // Integer cũng là Object.
~~~

Một biến khai báo kiểu `Number` có thể trỏ đến `Integer` hoặc `Double` vì chúng tương thích với `Number`. **Kiểu khai báo của biến vẫn là `Number`** sau khi gán lại, dù kiểu runtime của object thay đổi.

Compiler cũng giới hạn những method được gọi dựa trên **kiểu tham chiếu tại vị trí sử dụng**:

~~~java
CharSequence text = "Java";
System.out.println(text.length()); // Đúng: CharSequence có length().
// text.substring(1);              // Sai: CharSequence không khai báo substring().
~~~

Object thực tế có thể là `String`, nhưng compiler không tự cho gọi mọi method riêng của `String` qua biến kiểu `CharSequence`. Khi thật sự cần thao tác phụ thuộc kiểu runtime, hãy kiểm tra trước, ví dụ cú pháp Java 17 `if (item instanceof Integer i) { ... }`.

`null` có thể gán cho biến tham chiếu như `String name = null;`, nhưng không gán được cho primitive `int`. Gọi method trên tham chiếu `null` có thể gây `NullPointerException`.

## 4. Phép gán hợp lệ, chuyển rộng và chuyển hẹp

| Tình huống | Ví dụ | Kết quả |
| --- | --- | --- |
| Cùng kiểu | `int x = 10; x = 20;` | Hợp lệ |
| Mở rộng số nguyên | `byte b = 100; int x = b;` | Hợp lệ, giữ nguyên giá trị |
| `int` sang `long` | `int x = 100; long y = x;` | Hợp lệ |
| Chuyển hẹp có cast | `int x = 130; byte b = (byte) x;` | Hợp lệ về cú pháp, **b = -126** do chỉ giữ 8 bit thấp |
| Số thực sang số nguyên có cast | `int n = (int) 3.9;` | Hợp lệ, **n = 3** (phần lẻ bị bỏ) |
| Gán chuỗi cho số | `int x = "10";` | **Lỗi biên dịch** |
| Gán số sang boolean | `boolean b = 1;` | **Lỗi biên dịch** |
| Gán supertype sang subtype | `Object o = "Hi"; String s = o;` | **Lỗi biên dịch** nếu không có cast/kiểm tra kiểu phù hợp |

**Lưu ý khi chuyển rộng:** từ số nguyên sang `float`/`double` có thể mất độ chính xác với giá trị lớn, dù không cần cast. **Cast không bảo đảm giá trị còn nguyên**; nó chỉ cho phép một phép chuyển kiểu nhất định.

Một ngoại lệ thực tế ở mức compile time: `byte b = 100;` hợp lệ vì `100` là biểu thức hằng kiểu `int` nằm trong phạm vi `byte`; nhưng:

~~~java
int number = 100;
// byte b = number;  // Lỗi: number là biến int, không phải constant expression.
// byte b = 128;     // Lỗi: vượt phạm vi byte.
~~~

Đừng đánh đồng việc **giá trị đang nhỏ** với việc compiler cho phép mọi phép gán thu hẹp.

## 5. Chương trình Java 17+ có thể biên dịch và chạy

Tạo file **DeclaredTypeDemo.java**:

~~~java
public class DeclaredTypeDemo {
    public static void main(String[] args) {
        byte small = 100;
        int quantity = small;
        long revenue = 3_000_000_000L;
        double average = quantity / 4.0;
        boolean available = true;
        char grade = 'A';

        CharSequence text = "Java 17";
        Number number = Integer.valueOf(42);
        number = Double.valueOf(2.5);

        Object item = "book";
        item = Integer.valueOf(7);

        byte narrowed = (byte) 130;
        int whole = (int) 3.9;

        var inferred = 10; // Compiler suy ra int.
        inferred = 12;
        final int MAX = 20;

        System.out.println("quantity=" + quantity);
        System.out.println("revenue=" + revenue);
        System.out.println("average=" + average);
        System.out.println("available=" + available + ", grade=" + grade);
        System.out.println("text=" + text);
        System.out.println("number=" + number);
        System.out.println("item=" + item);
        System.out.println("narrowed=" + narrowed + ", whole=" + whole);
        System.out.println("inferred=" + inferred + ", MAX=" + MAX);

        if (item instanceof Integer value) {
            System.out.println("nextItem=" + (value + 1));
        }
    }
}
~~~

Trong terminal (Bash, PowerShell hoặc Command Prompt) tại thư mục chứa file:

~~~bash
javac -encoding UTF-8 DeclaredTypeDemo.java
java DeclaredTypeDemo
~~~

**Expected output:**

~~~text
quantity=100
revenue=3000000000
average=25.0
available=true, grade=A
text=Java 17
number=2.5
item=7
narrowed=-126, whole=3
inferred=12, MAX=20
nextItem=8
~~~

Đọc kết quả: `quantity` nhận giá trị `byte` dưới dạng `int`; `number` giữ kiểu khai báo `Number` nhưng trỏ tới object `Double` tại lúc in; `narrowed` minh họa chuyển hẹp mất thông tin; `item instanceof Integer value` kiểm tra kiểu object trước khi dùng `value` như `Integer`.


## 6. `var` giữ kiểu tĩnh; `final` hạn chế gán lại

`var` cho phép suy luận kiểu từ initializer ở vị trí được hỗ trợ, nhưng kiểu suy ra vẫn cố định:

~~~java
var count = 10;    // int
count = 20;        // Hợp lệ
// count = "twenty"; // Lỗi kiểu
// var unknown = null; // Không suy ra được kiểu từ null đơn lẻ
~~~

`final` là ràng buộc **số lần gán cho biến**, độc lập với kiểu khai báo:

~~~java
final Number max = Integer.valueOf(10);
// max = Double.valueOf(3.5); // Lỗi: final không cho gán lại
~~~

Vì vậy, câu hỏi “giá trị này **có thể gán vì tương thích kiểu không?**” khác câu hỏi “**biến final này còn được phép gán không?**”. Quy tắc gán `final` theo luồng điều khiển và tính mutable của object được đào sâu ở hai bài riêng.

## 7. Bẫy thường gặp và cách tự kiểm tra

| Mảnh mã | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| `long n = 3_000_000_000;` | Literal thập phân chưa có `L` và quá lớn cho `int` | `3_000_000_000L` |
| `byte b = 128;` | Ngoài phạm vi `byte` | Dùng kiểu rộng hơn hoặc giá trị trong miền |
| `int x = 3.9;` | `double` không tự thu hẹp thành `int` | Xem có thực sự muốn `(int) 3.9` không |
| `String s = 100;` | `int` không được gán trực tiếp thành `String` | `String.valueOf(100)` |
| `var x = 10; x = "A";` | `var` đã suy luận `int` | Dùng biến kiểu phù hợp, không gán khác kiểu |
| `CharSequence t = "Hi"; t.substring(1);` | Kiểu khai báo không có method `substring` | Dùng `String` khi cần, hoặc kiểm tra/chuyển kiểu an toàn |
| `String s = null; s.length();` | Tham chiếu `null` không có object để gọi method | Kiểm tra `null` hoặc thiết kế tránh null |

### Bài tập ngắn

1. Dự đoán kiểu và giá trị của `var x = 5L;`, sau đó thử gán `x = 6;` và `x = "6";`. Tại sao kết quả khác nhau?
2. Giải thích vì sao `byte b = 100;` biên dịch được nhưng `int x = 100; byte b = x;` lại không.
3. Tạo `Number n = Integer.valueOf(3);` rồi gán `Double.valueOf(3.5)`. Kiểu khai báo của `n` có thay đổi không?
4. Thử `final StringBuilder b = new StringBuilder(); b.append("OK");`. Phân biệt thay đổi object với gán lại reference.
5. Trong `DeclaredTypeDemo`, thử thay `(byte) 130` bằng `(byte) 127` và dự đoán kết quả.

**Ghi nhớ:** Với **primitive**, kiểu khai báo xác định miền giá trị và cách biểu diễn. Với **reference**, kiểu khai báo giới hạn đối tượng tương thích và những thành phần có thể truy cập qua biến; object thực tế có thể là subtype. `var` chỉ giúp suy luận kiểu cố định; `final` chỉ hạn chế gán lại biến. Mỗi phép gán đều phải qua quy tắc kiểu của Java.
