# Raw type, unchecked warning và giới hạn nhận biết tham số kiểu lúc chạy

## 1. Ba khái niệm cần phân biệt

- **Raw type** là generic type được dùng mà không ghi type argument, ví dụ List thay vì List&lt;String&gt;.
- **Unchecked warning** báo rằng compiler không thể xác minh đầy đủ tính an toàn kiểu của một thao tác.
- **Type erasure** là cơ chế triển khai generics: type argument giúp kiểm tra mã nguồn, nhưng không tạo một runtime class riêng cho từng đối số kiểu.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
String name = names.get(1); // Có thể ném ClassCastException.
~~~

raw trỏ đến cùng object với names. Dòng raw.add(42) thường biên dịch kèm cảnh báo; khi đọc phần tử 42 qua List&lt;String&gt;, compiler chèn cast về String và cast thất bại. Lỗi vì vậy có thể xuất hiện tại nơi đọc dữ liệu sai kiểu, xa nơi dữ liệu được thêm vào.

## 2. Raw type khác List<?> và List&lt;Object&gt;

| Khai báo | Ý nghĩa | Có thể thêm String? | An toàn kiểu |
| --- | --- | --- | --- |
| List raw | Bỏ qua type argument | Có, thường có warning | Thấp |
| List<?> | Kiểu phần tử chưa biết | Không thêm giá trị tùy ý, ngoại trừ null | Compiler vẫn bảo vệ kiểu |
| List&lt;Object&gt; | Danh sách có phần tử kiểu Object | Có | Kiểm tra kiểu ở compile time |

Dùng List<?> khi chỉ cần đọc/in các phần tử bất kể kiểu. List&lt;String&gt; không phải subtype của List&lt;Object&gt; vì generic là bất biến. Raw type chủ yếu tồn tại để tương thích với thư viện Java cũ; trong code mới, ưu tiên type argument đầy đủ hoặc wildcard phù hợp.

## 3. Ví dụ chạy được: warning và lỗi lúc đọc

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        List raw = names;
        raw.add(42);

        System.out.println("first=" + names.get(0));
        try {
            String second = names.get(1);
            System.out.println("second=" + second);
        } catch (ClassCastException ex) {
            System.out.println("read failed=" + ex.getClass().getSimpleName());
        }

        List<Integer> numbers = new ArrayList<>();
        System.out.println("same runtime class="
                + (names.getClass() == numbers.getClass()));
        System.out.println("instanceof List<?>=" + (names instanceof List<?>));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked RawTypeDemo.java
java RawTypeDemo
~~~

Kết quả stdout:

~~~text
first=An
read failed=ClassCastException
same runtime class=true
instanceof List<?>=true
~~~

Khi biên dịch, javac đưa ra warning về raw type và unchecked invocation tại các dòng khai báo/gọi qua raw. Số dòng cụ thể phụ thuộc vị trí mã nguồn. Hai ArrayList có type argument khác nhau vẫn có cùng runtime class; instanceof List<?> chỉ xác nhận object là List, không chứng minh danh sách chứa String.

## 4. Type erasure và reifiable types

Với type parameter không bound, erasure thường là Object; với T extends Number, erasure là Number. List&lt;String&gt; và List&lt;Integer&gt; đều có runtime class là List/ArrayList, không phải hai class riêng.

Vì runtime không giữ type argument như một kiểu riêng có thể kiểm tra trực tiếp, các biểu thức sau không hợp lệ:

~~~java
// Không hợp lệ:
if (value instanceof List<String>) { }
Class<?> type = List<String>.class;
List<String>[] values = new List<String>[10];
~~~

Có thể kiểm tra **instanceof List<?>** rồi xác thực từng phần tử nếu ứng dụng cần chắc chắn dữ liệu là String. Reflection có thể đọc metadata generic của khai báo field/method nếu class file lưu metadata đó; điều này không có nghĩa từng object ArrayList giữ type argument thực tế của nó.

Nếu ứng dụng cần thông tin kiểu lúc chạy, hãy truyền Class&lt;T&gt;, schema hoặc validator rõ ràng. Đừng giả định generic type argument luôn tồn tại trên từng object.

## 5. Cách xử lý warning

1. Đổi raw type sang kiểu tham số hóa như List&lt;String&gt; nếu biết kiểu phần tử.
2. Dùng List<?> nếu chỉ cần đọc mà không phụ thuộc kiểu phần tử.
3. Kiểm tra nguồn dữ liệu trước unchecked conversion/cast; nếu cần, xác thực từng phần tử.
4. Nếu buộc phải tích hợp API legacy, cô lập raw type tại ranh giới tương thích và chuyển dữ liệu sang kiểu an toàn càng sớm càng tốt.
5. Chỉ dùng @SuppressWarnings("unchecked") khi có bằng chứng cho giả định kiểu, và giới hạn annotation ở phạm vi nhỏ nhất. Annotation chỉ ẩn warning, không thêm kiểm tra runtime.

Raw type và unchecked cast có thể phá vỡ các bảo đảm compile time, còn type erasure giải thích vì sao lỗi đôi khi chỉ xuất hiện lúc đọc. Không dùng suppression để che một giả định kiểu chưa được kiểm chứng.

## 6. Tự kiểm tra

- Raw type khác List&lt;Object&gt; thế nào? Raw type bỏ qua type argument; List&lt;Object&gt; vẫn được compiler kiểm tra.
- Vì sao List&lt;String&gt; không thể xác nhận bằng instanceof? Runtime không kiểm tra type argument cụ thể.
- Warning unchecked có nghĩa chắc chắn chương trình hỏng không? Không; nó có nghĩa compiler không thể bảo đảm an toàn kiểu.
- Vì sao lỗi có thể xuất hiện ở get() thay vì add()? Cast về kiểu khai báo được chèn ở nơi đọc có thể thất bại.
- Khi cần xác minh dữ liệu runtime, nên làm gì? Kiểm tra từng phần tử hoặc dùng schema/type token tường minh.

Tài liệu tham khảo chính thức: JLS Java SE 17 §4.6 Type Erasure, §4.7 Reifiable Types, §4.8 Raw Types, §5.1.9 Unchecked Conversion và §5.5.2 Checked and Unchecked Casts.