# `var` suy luận kiểu biến cục bộ từ biểu thức khởi tạo — Java 17+

Từ Java 10, `var` cho phép **trình biên dịch suy ra kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo. Đây là thay đổi về cú pháp khai báo: `var` không tạo kiểu dữ liệu mới, không làm Java trở thành ngôn ngữ kiểu động và không đổi kiểu biến theo các lần gán tiếp theo.

~~~java
var count = 10;        // int count = 10;
var title = "Java";    // String title = "Java";
var active = true;     // boolean active = true;
~~~

## 1. Compiler đọc kiểu của biểu thức bên phải

Khi gặp `var name = expression;` ở vị trí được phép, compiler kiểm tra `expression`, xác định kiểu của nó, rồi dùng kiểu ấy để kiểm tra mọi câu lệnh tiếp theo. Compiler không chạy chương trình để quan sát giá trị và không suy luận ngược từ các phép gán sau khai báo.

| Biểu thức khởi tạo | Kiểu tĩnh suy ra | Điều cần chú ý |
| --- | --- | --- |
| `10` | `int` | Literal nguyên không hậu tố thường là `int` |
| `10L` | `long` | `L` chọn literal `long` |
| `2.5` | `double` | Literal thực mặc định là `double` |
| `"Java"` | `String` | Kiểu chuỗi đã rõ |
| `Integer.valueOf(7)` | `Integer` | Kiểu trả về đã khai báo của method |
| `new int[]{1, 2}` | `int[]` | Biểu thức tạo mảng mang kiểu cụ thể |
| `java.util.List.of("A", "B")` | `List<String>` | Tham số generic suy ra từ đối số |
| `new java.util.ArrayList<String>()` | `ArrayList<String>` | Kiểu lớp triển khai và phần tử đã rõ |

Với `var count = 10;`, compiler chấp nhận `count = 20;` nhưng từ chối `count = "20";`. Thay `var` bằng `int` trong cùng khai báo không thay đổi phép kiểm tra kiểu.

## 2. Ví dụ chạy độc lập trên JDK 17+

Lưu chương trình dưới tên **`VarInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class VarInferenceDemo {
    private static String findTitle(boolean found) {
        return found ? "Guide" : null;
    }

    public static void main(String[] args) {
        var copies = 3;                         // int
        var language = "Java";                  // String
        var labels = List.of("red", "blue");     // List<String>
        var editable = new ArrayList<String>(); // ArrayList<String>
        editable.add(labels.get(0));
        // editable.add(7); // Lỗi biên dịch: cần String.

        var total = 0;                          // int
        for (var value : new int[]{2, 4, 6}) { // value là int
            total += value;
        }

        var title = findTitle(false);           // String, giá trị null
        // copies = "many"; // Lỗi biên dịch: copies là int.

        System.out.println("copies=" + copies);
        System.out.println("language=" + language);
        System.out.println("labels=" + labels);
        System.out.println("editable=" + editable);
        System.out.println("total=" + total);
        System.out.println("titleIsNull=" + (title == null));
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac --release 17 -encoding UTF-8 VarInferenceDemo.java
java VarInferenceDemo
~~~

Kết quả:

~~~text
copies=3
language=Java
labels=[red, blue]
editable=[red]
total=12
titleIsNull=true
~~~

Trong chương trình trên, `findTitle` khai báo trả `String`, nên `title` có kiểu tĩnh `String` **ngay cả khi giá trị thực tế là `null`**. Vòng `for` suy ra kiểu phần tử từ mảng `int[]`; còn lời gọi `List.of` và constructor `ArrayList<String>` mang thông tin generic ở thời điểm biên dịch.

## 3. Biểu thức phải thể hiện kiểu mà bạn thực sự muốn

`var` suy luận từ **initializer hiện tại**; compiler không dùng các lệnh sau để đoán kiểu phần tử của một collection:

~~~java
var mixed = new ArrayList<>();    // ArrayList<Object>
mixed.add("red");
mixed.add(7);                     // Hợp lệ với ArrayList<Object>.

var names = new ArrayList<String>();
names.add("red");
// names.add(7);                  // Không hợp lệ: cần String.
~~~

Nếu cần kiểu tĩnh là interface, viết kiểu ấy ở phía trái:

~~~java
List<String> otherNames = new ArrayList<>();
~~~

Ở khai báo này, `List<String>` thể hiện mức trừu tượng mong muốn và cung cấp kiểu đích cho diamond `<>`. Với `var`, kiểu biến ở ví dụ trước là `ArrayList<String>`, không tự chuyển thành `List<String>` dù class triển khai interface đó.

## 4. Những ranh giới để đọc các bài tiếp theo

- **Kiểm tra kiểu tĩnh:** `var` vẫn tuân thủ phép gán, overload, generic và truy cập method/field; ví dụ chuyên sâu nằm ở bài “var giữ nguyên kiểm tra kiểu tĩnh”.
- **Vị trí khai báo:** `var` áp dụng cho các vị trí local hợp lệ, vòng lặp, resource và tham số lambda theo quy tắc riêng; không dùng làm kiểu field hoặc return type.
- **Nguồn suy kiểu:** local `var` thông thường cần initializer; `var x;` không hợp lệ. `var x = null;` và `var a = {1, 2};` cũng không hợp lệ, trong khi `var a = new int[]{1, 2};` hợp lệ.
- **Biểu thức số:** `var ratio = 5 / 2;` nhận `int` với giá trị `2`. Phép chia nguyên diễn ra trước suy luận; bài về literal và phép tính số giải thích promotion, cast và overflow.
- **Dễ đọc:** initializer đủ kiểu cho compiler chưa chắc đủ rõ với người đọc. Có lúc `List<String> names = ...` diễn đạt ý đồ tốt hơn.

Những quy tắc trên cùng xuất phát từ một điểm: **`var` nhận kiểu của biểu thức ở vị trí khai báo, rồi Java áp dụng hệ thống kiểu bình thường**.

## 5. Tự kiểm tra

1. `var n = 1; var m = 1L;` suy ra kiểu nào? **Đáp án:** `int`, `long`.
2. Vì sao `var x = Integer.valueOf(7);` không suy ra `int`? **Đáp án:** `valueOf` trả `Integer`.
3. `var list = new ArrayList<>();` có tự suy ra `ArrayList<String>` từ `list.add("A")` không? **Đáp án:** Không; ở đây là `ArrayList<Object>`.
4. `var value = findTitle(false);` có hợp lệ nếu method trả `String` nhưng giá trị `null` không? **Đáp án:** Có, kiểu tĩnh từ chữ ký method là `String`.
5. Nếu muốn biến mang kiểu interface `List<String>` thay vì class `ArrayList<String>`, viết thế nào? **Đáp án:** `List<String> names = new ArrayList<>();`.

**Ghi nhớ:** Hãy xác định kiểu của biểu thức khởi tạo, kiểm tra kiểu suy ra có đúng ý đồ không và dùng khai báo tường minh khi điều đó giúp người đọc hiểu nhanh hơn.
