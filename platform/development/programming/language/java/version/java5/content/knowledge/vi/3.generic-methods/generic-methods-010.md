# Phân biệt phương thức generic với phương thức nhận Object

## 1. Cùng nhận nhiều kiểu dữ liệu, nhưng hợp đồng khác nhau

Một phương thức nhận `Object` có thể tiếp nhận nhiều loại đối tượng vì các kiểu tham chiếu như `String`, `Integer` hay `List<String>` đều có thể được nhìn dưới kiểu `Object`. Điều đó không làm phương thức trở thành generic.

Phương thức generic tự khai báo tham số kiểu, chẳng hạn `<T>`, để biểu diễn một quan hệ kiểu có thể được giữ lại tại nơi gọi. Sự khác biệt quan trọng là **thông tin nào được liên kết và được trình biên dịch bảo đảm**, không chỉ là số loại đối tượng có thể truyền vào.

Xét hai phương thức cùng chọn giá trị đầu tiên khác `null`:

```java
static Object orObject(Object value, Object fallback) {
    return value != null ? value : fallback;
}

static <T> T orTyped(T value, T fallback) {
    return value != null ? value : fallback;
}
```

Đây là hai khai báo đặt trong một lớp, chưa phải chương trình chạy độc lập. Tên khác nhau được dùng để dễ so sánh.

- `orObject` nhận hai giá trị qua kiểu `Object` và chỉ hứa kết quả có kiểu tĩnh là `Object`.
- `orTyped` dùng cùng tham số kiểu `T` cho hai đối số và kiểu trả về. Bên gọi có thể nhận trực tiếp một kết quả phù hợp với đối số kiểu đã được chọn cho lời gọi.

Cả hai có cùng thuật toán lựa chọn trong ví dụ. Generic thay đổi hợp đồng kiểm tra kiểu; nó không tự thay thuật toán xử lý `null`. Các ví dụ trong bài dùng kiến thức còn áp dụng trong Java hiện hành và chạy với Java 17 trở lên.

## 2. Phương thức nhận Object làm mất quan hệ kiểu nào?

Với hai đối số chuỗi:

```java
Object label = orObject(null, "untitled");
// String text = orObject(null, "untitled"); // Lỗi biên dịch.
```

Người viết nhìn thấy giá trị dự phòng là chuỗi, nhưng chữ ký chỉ khai báo kết quả `Object`. Trình biên dịch không phân tích phần thân để tạo một kiểu trả về chuyên biệt cho từng cách truyền đối số.

Muốn dùng API riêng của `String`, có thể kiểm tra kiểu thực tế:

```java
if (label instanceof String text) {
    System.out.println(text.length());
}
```

Đoạn này dùng pattern matching của `instanceof`, hỗ trợ trong Java 17 trở lên. Nếu `label` không phải chuỗi hoặc là `null`, nhánh không chạy.

Ép kiểu trực tiếp là một lựa chọn có kiểm tra khi chạy nhưng cần có cơ sở:

```java
String text = (String) orObject(null, "untitled");
```

Với đúng dữ liệu trên, phép ép kiểu thành công. Nhưng hợp đồng của `orObject` cũng cho phép `orObject(null, 404)`. Ép kết quả ấy sang `String` gây `ClassCastException` vì số nguyên đã được boxing thành `Integer`, không phải chuỗi.

Phương thức không sai chỉ vì nhận `Object`. Vấn đề là chữ ký ấy không diễn đạt được yêu cầu “kết quả giữ kiểu mà bên gọi đang cần từ đầu vào” nếu đó là điều API muốn bảo đảm.

## 3. Phương thức generic giữ quan hệ kiểu tại nơi gọi

```java
String title = orTyped(null, "untitled");
Integer retries = orTyped(null, 3);
```

Với các lời gọi này, ràng buộc của đối số và kiểu đích cho phép trình biên dịch chọn đối số kiểu phù hợp lần lượt với `String` và `Integer`. Bên gọi không cần viết phép ép kiểu để nhận kết quả.

Nếu cố đặt yêu cầu mâu thuẫn:

```java
// String bad = orTyped(null, 404); // Lỗi biên dịch.
```

Hợp đồng generic khiến sai lệch giữa đầu vào và kiểu kết quả mong muốn được phát hiện trước khi chạy. Không cần đợi một phép ép kiểu thất bại.

Tuy nhiên, cùng `T` **không bắt buộc các đối số có cùng lớp thực tế**. Lời gọi dưới đây có thể dùng một kiểu tham chiếu chung phù hợp:

```java
Object broad = orTyped("note", 99);
```

Nó hợp lệ và trả về chuỗi `"note"` vì đối số thứ nhất khác `null`. Khi biến kết quả được khai báo là `Object`, bên gọi vẫn chỉ có hợp đồng của `Object`. Nếu cần kết quả chắc chắn là chuỗi, dùng đầu vào và ngữ cảnh đáp ứng điều đó; generic không biến số thành chuỗi hoặc buộc một kiểu chung phải luôn là kiểu hẹp nhất mà người viết mong muốn.

## 4. So sánh trực tiếp

| Tiêu chí | `Object orObject(Object, Object)` | `<T> T orTyped(T, T)` |
| --- | --- | --- |
| Tự khai báo tham số kiểu | Không | Có, bằng `<T>` |
| Nhận được nhiều loại đối tượng | Có | Có, theo ràng buộc của từng lời gọi |
| Liên kết kiểu đầu vào với kiểu trả về | Chỉ qua hợp đồng rộng `Object` | Qua cùng tham số kiểu `T` |
| Kết quả của lời gọi với chuỗi, xét qua chữ ký | `Object` | Có thể nhận dưới `String` khi các ràng buộc phù hợp |
| Phát hiện yêu cầu trả `String` từ dự phòng số nguyên | Cần kiểm tra/ép kiểu ở nơi dùng; ép sai có thể lỗi khi chạy | Có thể bị từ chối ngay khi biên dịch |
| Mặc nhiên loại bỏ `null` | Không | Không |
| Mặc nhiên chuyển đổi hoặc sao chép đối tượng | Không | Không |

Generic giúp giữ thông tin kiểu khi hợp đồng có quan hệ cần biểu đạt. Nếu đầu vào hoặc biến bên gọi đã có kiểu rộng `Object`, phương thức generic không tự khôi phục thông tin kiểu hẹp chỉ nhờ biết lớp thực tế lúc chạy.

Ví dụ, `Object input = "abc"; Object output = orTyped(input, "fallback");` không cung cấp một kết quả chắc chắn có kiểu `String` cho mọi giá trị mà biến `input` được phép giữ.

## 5. Quan hệ kiểu còn quan trọng khi kết quả là collection

So sánh hai phương thức tạo danh sách một phần tử:

```java
static java.util.List<Object> boxObject(Object value) {
    return java.util.Collections.singletonList(value);
}

static <T> java.util.List<T> boxTyped(T value) {
    return java.util.Collections.singletonList(value);
}
```

`boxObject("safe")` trả về `List<Object>`. `boxTyped("safe")` có thể được nhận trực tiếp dưới `List<String>`:

```java
java.util.List<String> typed = boxTyped("safe");
String first = typed.get(0);

java.util.List<Object> broad = boxObject("safe");
Object item = broad.get(0);
// java.util.List<String> wrong = boxObject("safe"); // Lỗi biên dịch.
```

Hai danh sách có thể in ra cùng nội dung `[safe]`, nhưng chữ ký cung cấp các bảo đảm khác nhau. `List<Object>` không phải kiểu cha chung cho mọi `List<T>`; nó không tự chuyển thành `List<String>` chỉ vì phần tử hiện tại là chuỗi.

Cả hai phương thức trong ví dụ trả về danh sách do `Collections.singletonList` tạo ra, không cho thêm, xóa hoặc thay thế phần tử. Generic không quyết định khả năng thay đổi của collection. Nó cũng không sao chép sâu phần tử; danh sách giữ tham chiếu đến đối tượng được truyền vào.

## 6. Chương trình chạy đầy đủ

Lưu thành **`GenericVsObjectDemo.java`**:

```java
import java.util.Collections;
import java.util.List;

public class GenericVsObjectDemo {
    static Object orObject(Object value, Object fallback) {
        return value != null ? value : fallback;
    }

    static <T> T orTyped(T value, T fallback) {
        return value != null ? value : fallback;
    }

    static List<Object> boxObject(Object value) {
        return Collections.singletonList(value);
    }

    static <T> List<T> boxTyped(T value) {
        return Collections.singletonList(value);
    }

    public static void main(String[] args) {
        String title = orTyped(null, "untitled");
        Integer retries = orTyped(null, 3);
        System.out.println("typed=" + title);
        System.out.println("next=" + (retries + 1));

        Object objectResult = orObject(null, "untitled");
        if (objectResult instanceof String text) {
            System.out.println("checked length=" + text.length());
        }

        try {
            String wrong = (String) orObject(null, 404);
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("cast rejected");
        }

        List<String> words = boxTyped("safe");
        System.out.println("boxed length=" + words.get(0).length());

        Object broad = orTyped("note", 99);
        System.out.println("wide=" + broad);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all GenericVsObjectDemo.java
java GenericVsObjectDemo
```

Stdout chính xác:

```text
typed=untitled
next=4
checked length=8
cast rejected
boxed length=4
wide=note
```

Khối `try/catch` cố ý minh họa một phép ép kiểu sai và bắt lỗi để chương trình tiếp tục. Các dòng generic không cần phép ép kiểu thủ công để nhận chuỗi, số nguyên hoặc phần tử chuỗi của danh sách.

## 7. Bên trong phương thức generic không tự biết API của mọi kiểu cụ thể

Khi khai báo `<T>` không có giới hạn rõ ràng, giới hạn trên mặc định là `Object`. Phần thân phải hợp lệ với mọi cách chọn đối số kiểu được hợp đồng cho phép.

```java
// Không hợp lệ:
// static <T> int length(T value) { return value.length(); }
```

`T` có thể là `Integer`, nên không được gọi `length()` như thể luôn là `String`. Hai cách thiết kế phù hợp hơn, tùy yêu cầu:

```java
static int lengthOfText(CharSequence value) {
    return value.length();
}

static <T extends CharSequence> T keepText(T value) {
    return value;
}
```

Phương thức thứ nhất chỉ cần khả năng đọc độ dài và trả về `int`, nên tham số `CharSequence` đủ diễn đạt nhu cầu. Phương thức thứ hai cố ý giữ quan hệ kiểu đầu vào–đầu ra: truyền `StringBuilder` có thể nhận lại dưới kiểu `StringBuilder` khi ngữ cảnh phù hợp, thay vì chỉ nhận `CharSequence`.

Không thêm `<T>` vào mọi phương thức nhận `Object` một cách máy móc. Hãy xác định quan hệ kiểu nào thật sự có giá trị cho bên gọi.

## 8. Khi nào Object là lựa chọn đúng?

Một số thao tác chỉ cần hành vi chung của mọi đối tượng, chẳng hạn in giá trị hoặc kiểm tra tính bằng nhau theo hợp đồng `equals`.

```java
static void display(Object value) {
    System.out.println(value);
}
```

Đổi thành `<T> void display(T value)` không tạo ra mối quan hệ hữu ích giữa nhiều vị trí trong chữ ký ở ví dụ đơn giản này. Phương thức không trả lại `T`, không đưa `T` vào một cấu trúc có kiểu và không liên kết nó với đối số thứ hai.

Thư viện chuẩn cũng phản ánh cách chọn theo nhu cầu:

- `Objects.equals(Object a, Object b)` nhận hai `Object` và trả về `boolean`; không cần giữ kiểu của một đầu vào làm kiểu kết quả.
- `Objects.requireNonNullElse(T obj, T defaultObj)` là phương thức generic; kiểu `T` liên kết hai đầu vào với kiểu giá trị được trả lại.

`Objects.requireNonNullElse` không có cùng hợp đồng `null` hoàn toàn với hàm minh họa trong bài: nó ném `NullPointerException` nếu cả hai đối số đều `null`, trong khi `orTyped` của bài trả về `null` ở trường hợp đó. Quan hệ kiểu và quy tắc giá trị là hai phần hợp đồng cần đọc riêng.

## 9. Xóa kiểu không làm hai cách khai báo tương đương về hợp đồng

Với `<T>` không có giới hạn tường minh, kiểu sau xóa kiểu của `T` là `Object`. Vì vậy, các tham số và kết quả của `orTyped` có thể được biểu diễn qua `Object` trong descriptor JVM. Nhưng thông tin generic vẫn giúp trình biên dịch kiểm tra các lời gọi, giữ chữ ký generic trong class file và chèn các thao tác cần thiết ở nơi dùng.

Không suy luận rằng “sau xóa kiểu đều là Object, nên viết cách nào cũng như nhau”. Khác biệt ở hợp đồng mã nguồn là lý do dòng gán sang `String` có thể đúng với `orTyped` nhưng sai với `orObject`.

Điều này cũng giải thích vì sao không thể khai báo hai overload chỉ khác nhau như sau trong cùng lớp:

```java
// Không thể cùng tồn tại:
// static Object select(Object value, Object fallback) { ... }
// static <T> T select(T value, T fallback) { ... }
```

Sau xóa kiểu, chúng xung đột ở danh sách kiểu tham số. Thêm tên tham số kiểu không tạo ra một overload khác biệt. Các hàm của chương trình dùng tên riêng để cùng xuất hiện nhằm so sánh.

Generic cũng không miễn nhiễm với mọi lỗi khi chạy. Dữ liệu `null`, chỉ số danh sách sai, ép kiểu không được kiểm tra hoặc một phần thân cố phá vỡ hợp đồng vẫn có thể gây lỗi. Không viết một phương thức `<T> T` nhận `Object` rồi ép tùy ý sang `T` để hứa trả bất kỳ kiểu nào bên gọi muốn; đó là một hợp đồng không có cơ sở từ dữ liệu đầu vào.

## 10. Cách chọn chữ ký khi viết API

Trước khi chọn generic hoặc `Object`, hãy trả lời:

1. Phương thức chỉ cần hành vi chung của `Object`, hay một khả năng cụ thể như `CharSequence` đã đủ?
2. Kiểu kết quả có cần giữ quan hệ với kiểu đối số không?
3. Có nhiều tham số hoặc collection cần liên kết cùng một kiểu phần tử không?
4. Chính sách `null`, thay đổi đối tượng và ngoại lệ được bảo đảm bằng cách nào, ngoài kiểm tra kiểu?

Nếu có quan hệ kiểu cần giữ, khai báo tham số kiểu để trình biên dịch hỗ trợ bên gọi. Nếu không có quan hệ ấy, dùng một kiểu cụ thể, một giao diện phù hợp hoặc `Object` có thể làm API dễ hiểu hơn.

## 11. Tự thực hành

1. Đổi `orTyped(null, "untitled")` thành `orTyped(null, 404)` và vẫn gán vào `String`. Quan sát lỗi biên dịch; so sánh với lỗi `ClassCastException` đã được bắt trong chương trình.
2. Thêm `StringBuilder builder = keepText(new StringBuilder("hi"))` vào một chương trình có phương thức `keepText`. Kiểm tra bên gọi giữ được khả năng gọi `append` mà không cần ép kiểu.
3. Gọi cả hai hàm với hai đối số `null`. Giải thích vì sao kiểm tra generic không tạo ra một giá trị khác `null`.
4. So sánh `boxObject("a")` và `boxTyped("a")` khi gán vào `List<String>`. Không ép kiểu cả danh sách để bỏ qua lỗi.
5. Viết một phương thức chỉ in đối tượng và một phương thức tạo danh sách cùng kiểu với đối số. Giải thích chữ ký nào cần generic để mang lại lợi ích cho bên gọi.

Phương thức generic hữu ích khi cần diễn đạt quan hệ kiểu xuyên qua hợp đồng. Phương thức nhận `Object` hữu ích khi một hợp đồng chung là đủ. Chọn đúng giúp lỗi kiểu xuất hiện ở nơi khai báo hoặc lời gọi, thay vì chỉ lộ ra khi một phép ép kiểu thất bại lúc chạy.

## Tài liệu đối chiếu

- [JLS §8.4.4 — Generic Methods](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.4): hợp đồng phương thức có tham số kiểu.
- [JLS §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): xóa kiểu của tham số kiểu và chữ ký phương thức.
- [JLS §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.5): kiểm tra và chuyển đổi ép kiểu.
- [Objects — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html): đối chiếu `equals` và `requireNonNullElse`.
