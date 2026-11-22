# Phân biệt `var` với kiểu động và `Object` trong Java (Java 10+)

## 1. Mục tiêu

Sau bài này, bạn có thể:
- Giải thích vì sao `var` là **suy luận kiểu cục bộ tại thời điểm biên dịch**, không biến Java thành ngôn ngữ kiểu động.
- Phân biệt **kiểu tĩnh của biến** với **kiểu thực tế của đối tượng lúc chạy**.
- Chọn đúng giữa `var`, khai báo kiểu tường minh và `Object`, đặc biệt khi dùng phương thức, generic và đa hình.
- Nhận biết các khai báo `var` không hợp lệ và những trường hợp suy luận kiểu dễ gây nhầm lẫn.

Bài áp dụng cho Java hiện đại (Java 17+); tính năng `var` cho biến cục bộ có từ Java 10.

## 2. So sánh nhanh ba khái niệm

| Tiêu chí | `var` trong Java | `Object` trong Java | Biến trong ngôn ngữ kiểu động (ví dụ JavaScript) |
| --- | --- | --- | --- |
| Bản chất | Cú pháp để trình biên dịch **suy ra kiểu tĩnh** từ biểu thức khởi tạo | **Kiểu tham chiếu** có tên, là lớp gốc của các lớp Java | Biến có thể nhận các giá trị thuộc những kiểu khác nhau; việc kiểm tra nhiều thao tác phụ thuộc thời điểm chạy |
| Xác định kiểu của biến | Ngay lúc biên dịch khai báo | Tường minh là `Object` lúc biên dịch | Không cố định một kiểu tĩnh cho biến theo cách của Java |
| Có thể gán giá trị khác kiểu? | Chỉ khi giá trị **tương thích với kiểu đã suy ra** | Có thể gán tham chiếu thuộc các lớp con của `Object` (kể cả giá trị nguyên thủy được boxing), nhưng biến vẫn có kiểu tĩnh `Object` | Có, ví dụ chuỗi rồi số trong JavaScript |
| Phương thức được phép gọi | Dựa vào kiểu tĩnh **đã suy ra** | Dựa vào kiểu tĩnh `Object`; muốn dùng API riêng của lớp con cần kiểm tra/ép kiểu phù hợp | Thường được kiểm tra khi thực thi |
| Có làm Java thành kiểu động? | Không | Không | Đây là cơ chế của chính ngôn ngữ kiểu động, không phải của Java |

**Nguyên tắc cốt lõi:** `var` không phải một kiểu dữ liệu tên là “var”; `Object` mới thực sự là một kiểu. Java vẫn kiểm tra tính tương thích kiểu tại thời điểm biên dịch trong cả hai cách khai báo.

## 3. `var`: trình biên dịch suy ra một kiểu và giữ nguyên kiểu đó

Ví dụ:

~~~java
var language = "Java";   // Trình biên dịch suy ra String
language = "Java 21";    // Hợp lệ: vẫn là String
// language = 21;        // Lỗi biên dịch: int không gán được cho String

var count = 10;          // Suy ra int, không phải Integer hay Object
count = count + 5;       // Hợp lệ
// count = 10L;          // Lỗi biên dịch: không tự chuyển long sang int

var boxed = Integer.valueOf(10); // Suy ra Integer
~~~

Về mặt kiểm tra kiểu, `var language = "Java";` tương đương `String language = "Java";`. Kiểu được quyết định **một lần từ kiểu của biểu thức khởi tạo**, không suy lại theo những giá trị gán về sau. `var` không ngầm chuyển mọi giá trị sang `Object`.

`var` cũng không có nghĩa là hằng số: biến vẫn có thể được gán lại bằng giá trị tương thích. Nếu muốn cấm gán lại, dùng `final var language = "Java";`.

**Suy luận theo kiểu tĩnh, không theo kiểu runtime:** với `var element = getElement();`, kiểu suy ra phụ thuộc kiểu trả về **được khai báo** của `getElement()`, dù đối tượng cụ thể khi chạy có thể thuộc lớp con.

## 4. `Object`: kiểu tĩnh rộng, đối tượng runtime có thể khác nhau

~~~java
Object value = "hello"; // Kiểu tĩnh: Object; đối tượng runtime: String
value = 42;             // Hợp lệ: int được boxing thành Integer
value = null;           // Hợp lệ với kiểu tham chiếu
// value.toUpperCase(); // Lỗi biên dịch: Object không khai báo toUpperCase()
~~~

Biến `value` **luôn có kiểu tĩnh `Object`** dù lần lượt trỏ tới `String`, `Integer` hay `null`. Khả năng gán đối tượng khác lớp xuất phát từ quan hệ kế thừa và boxing, không phải vì kiểu của biến tự thay đổi như trong JavaScript.

Muốn gọi hành vi chỉ có ở `String`, hãy kiểm tra kiểu thực tế rồi dùng biến đã được thu hẹp kiểu:

~~~java
Object value = "hello";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
~~~

Đây là cú pháp pattern matching cho `instanceof` được hỗ trợ trong Java hiện đại (từ Java 16). Nó bảo đảm thao tác trên `text` an toàn khi điều kiện đúng; không biến `Object` thành kiểu động.

Lưu ý:
- `Object` chứa tham chiếu, không chứa trực tiếp giá trị nguyên thủy `int`, `boolean`, ...; Java dùng boxing khi cần, ví dụ `Object o = 42;` tạo/nhận một `Integer`.
- Gọi `getClass()` cho biết lớp của đối tượng **không null** lúc chạy; nó không thay đổi kiểu tĩnh dùng để kiểm tra lời gọi phương thức.
- Gán `Object` cho biến có kiểu hẹp hơn đòi hỏi kiểm tra/ép kiểu phù hợp; ép sai có thể gây `ClassCastException`. Trong code ứng dụng, ưu tiên interface/kiểu cụ thể nếu biết hợp đồng dữ liệu.

## 5. Ví dụ hoàn chỉnh, biên dịch và chạy được trên Java 17+

Tạo tệp **VarVsObjectDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarVsObjectDemo {
    public static void main(String[] args) {
        var text = "Java 10"; // Kiểu tĩnh String
        text = text.toUpperCase();
        System.out.println("var text: " + text);

        var number = 10; // Kiểu tĩnh int
        number += 5;
        System.out.println("var number: " + number);

        Object value = "hello"; // Kiểu tĩnh Object
        value = 42;             // Runtime: Integer do boxing
        System.out.println(
                "Object runtime class: " + value.getClass().getSimpleName());

        value = "hello";
        if (value instanceof String s) {
            System.out.println("Pattern match: " + s.toUpperCase());
        }

        var names = new ArrayList<String>();
        names.add("An");
        System.out.println(
                "Inferred list item: " + names.get(0).toUpperCase());

        var objectTyped = (Object) "start"; // Suy ra Object, không phải String
        objectTyped = 99;
        System.out.println(
                "Cast to Object => " + objectTyped.getClass().getSimpleName());

        List<String> asInterface = new ArrayList<>();
        asInterface.add("Binh");
        System.out.println("Interface type item: " + asInterface.get(0));
    }
}
~~~

Chạy tại thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac VarVsObjectDemo.java
java VarVsObjectDemo
~~~

Kết quả chính xác:

~~~text
var text: JAVA 10
var number: 15
Object runtime class: Integer
Pattern match: HELLO
Inferred list item: AN
Cast to Object => Integer
Interface type item: Binh
~~~

Giải thích điểm khác biệt:
1. `text` và `number` có kiểu tĩnh rõ ràng dù khai báo bằng `var`; phương thức `toUpperCase()` hợp lệ vì `text` được suy ra là `String`.
2. `value` luôn là `Object`; `getClass()` phản ánh lớp `Integer` khi chạy, còn `instanceof String s` mới giúp sử dụng API của chuỗi an toàn.
3. `names` được suy ra là **ArrayList<String>** nên phần tử lấy ra có kiểu `String`, không cần ép kiểu.
4. `objectTyped` được suy ra là **Object** vì biểu thức khởi tạo được ép về `Object`. Điều này chứng minh `var` không tự ưu tiên kiểu runtime `String`.
5. `asInterface` có kiểu tĩnh `List<String>`, trong khi đối tượng thực tế là `ArrayList<String>`. Cách viết tường minh giữ hợp đồng API theo interface.

## 6. Vì sao `var` dễ gây hiểu nhầm với generic?

Xét hai khai báo:

~~~java
var data = new ArrayList<>(); // Thường được suy ra ArrayList<Object>
data.add("Java");             // Hợp lệ
data.add(10);                 // Hợp lệ: boxing thành Integer, cũng là Object

List<String> names = new ArrayList<>(); // Target type là List<String>
names.add("Java");                      // Hợp lệ
// names.add(10);                       // Lỗi biên dịch
~~~

Ở khai báo thứ nhất, không có kiểu phần tử đích đủ cụ thể nên toán tử kim cương `<>` suy ra `Object`. Việc nhận được cả chuỗi và số **không chứng tỏ `var` là kiểu động**: cấu trúc là `ArrayList<Object>`, mỗi phần tử thuộc kiểu tham chiếu tương thích với `Object`.

Muốn giữ kiểm tra kiểu phần tử, hãy nêu thông tin generic ở một trong hai phía:

~~~java
var names1 = new ArrayList<String>(); // ArrayList<String>
List<String> names2 = new ArrayList<>(); // List<String>
var names3 = List.of("An", "Binh");      // List<String>
~~~

`List.of` tạo danh sách không cho phép thêm/xóa phần tử. Dù dùng `var`, tính chất ấy của đối tượng **không thay đổi**.

Lưu ý về tính trừu tượng: `var names1 = new ArrayList<String>();` suy ra kiểu triển khai `ArrayList<String>`, trong khi `List<String> names2 = new ArrayList<>();` khai báo theo interface `List<String>`. Nếu hợp đồng code nên phụ thuộc interface, khai báo tường minh thường dễ bảo trì hơn.

## 7. Giới hạn cú pháp của `var` cần nhớ

`var` cho phép suy luận kiểu **biến cục bộ có biểu thức khởi tạo**; sử dụng được trong thân phương thức, khối lệnh, phần khởi tạo vòng `for`, vòng `for-each` và khai báo resource phù hợp trong `try-with-resources`. Nó không thay cho kiểu ở field, kiểu trả về, tham số phương thức hay tham số `catch`.

Các ví dụ **cố ý không biên dịch**:

~~~java
var missing;                  // Thiếu biểu thức khởi tạo
var nothing = null;           // Không suy ra kiểu chỉ từ null
var numbers = {1, 2, 3};      // Array initializer cần kiểu/khởi tạo mảng phù hợp
var mapper = s -> s.length(); // Lambda không có target functional interface
~~~

Cách viết đúng trong những trường hợp đó:

~~~java
String missing;
String nothing = null;
var numbers = new int[] {1, 2, 3};
java.util.function.Function<String, Integer> mapper = s -> s.length();
~~~

Từ Java 11, `var` còn dùng được trong **tham số lambda** theo quy tắc riêng (các tham số trong cùng lambda phải dùng nhất quán kiểu khai báo). Tính năng này không làm hợp lệ việc dùng `var` cho tham số của một phương thức Java thông thường.

Không thể gán trực tiếp một lambda hoặc method reference cho một biến `var` mà không có target functional interface; dùng kiểu như `Function<String, Integer>` khi cần.

## 8. So với kiểu động trong JavaScript

Mã JavaScript dưới đây là **đối chứng ngôn ngữ khác**, không phải mã Java:

~~~javascript
let value = "Java";
value = 42; // Hợp lệ: cùng một biến có thể lần lượt chứa chuỗi và số
~~~

Trong Java:

~~~java
var value = "Java";
// value = 42; // Lỗi biên dịch, vì value đã có kiểu tĩnh String

Object other = "Java";
other = 42;   // Hợp lệ, vì String và Integer đều tương thích Object
~~~

Điểm phân biệt quyết định là **kiểm tra phương thức và chuyển kiểu ở compile time**: khai báo `Object` không cho phép gọi trực tiếp phương thức riêng của `String`, bất kể lúc chạy biến đang tham chiếu tới chuỗi.

Đa hình runtime của Java cũng không phải kiểu động: một biến kiểu interface hoặc lớp cha có thể tham chiếu đối tượng lớp con và gọi phiên bản phương thức ghi đè của lớp con, nhưng lời gọi vẫn phải hợp lệ theo kiểu tĩnh của biến.

## 9. Chọn `var`, kiểu tường minh hay `Object`?

| Tình huống | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Biến cục bộ, kiểu dễ nhận ra ngay từ biểu thức tạo | `var user = new User(...);` | Giảm lặp tên kiểu mà vẫn giữ kiểm tra kiểu tĩnh |
| Muốn public API hoặc biến thể hiện interface, tăng rõ nghĩa | `List<String> users = new ArrayList<>();` | Bộc lộ hợp đồng trừu tượng và generic mong muốn |
| Biểu thức trả về kiểu khó đoán hoặc có rủi ro suy luận `Object` | Ghi rõ kiểu và tham số generic | Giúp người đọc và trình biên dịch giữ đúng mục tiêu |
| Cần lưu tham chiếu tới các đối tượng không chung interface phù hợp | `Object` trong phạm vi có kiểm tra kiểu rõ ràng | Đây là quyết định chọn kiểu rộng một cách tường minh, có đánh đổi về API và ép kiểu |
| Biến chỉ cần dùng trong một khối và không gán lại | `final var` hoặc `final String` | `final` kiểm soát việc gán lại, độc lập với suy luận kiểu |

Không chọn `Object` chỉ để “có thể gán mọi thứ” khi dữ liệu thực sự có một cấu trúc rõ ràng. Dùng interface, lớp hoặc generic thích hợp để tránh ép kiểu tràn lan và giảm lỗi runtime.

## 10. Tự kiểm tra nhanh

**Câu 1.** Với `var x = "hello";`, lệnh `x = 100;` có hợp lệ không? **Không.** `x` có kiểu tĩnh `String`, không nhận `int`.

**Câu 2.** Với `Object x = "hello";`, gọi `x.length()` có hợp lệ không? **Không.** Kiểu tĩnh `Object` không có `length()`; cần kiểm tra kiểu và dùng biến `String`.

**Câu 3.** Với `var x = (Object) "hello";`, sau đó `x = 100;` có hợp lệ không? **Có.** Biểu thức khởi tạo có kiểu tĩnh `Object`, nên `x` cũng là `Object`; `100` được boxing.

**Câu 4.** Vì sao `var list = new ArrayList<>();` có thể nhận cả `"A"` và `1`? Vì kiểu phần tử được suy ra là `Object` khi thiếu thông tin đích, **không phải** vì kiểu của biến thay đổi lúc chạy.

**Ghi nhớ:** `var` = để trình biên dịch **viết hộ tên kiểu tĩnh**; `Object` = **tên một kiểu tĩnh rộng**; kiểu động = cơ chế khác, không được kích hoạt bằng `var` hoặc `Object` trong Java.