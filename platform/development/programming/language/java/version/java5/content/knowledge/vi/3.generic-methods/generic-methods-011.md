# Nạp chồng phương thức generic và lỗi không xác định được lời gọi

## 1. Khái niệm: cùng tên chưa đủ để biết phương thức nào được gọi

Nạp chồng (overloading) cho phép nhiều phương thức cùng tên nhưng có các danh sách tham số phân biệt được theo quy tắc Java. Một hoặc nhiều phương thức trong nhóm có thể là generic.

Ví dụ:

```java
// Các phương thức minh họa, đặt bên trong cùng một lớp.
static <T> String inspect(T value) {
    return "generic";
}

static String inspect(String value) {
    return "String";
}
```

Khi gặp `inspect(...)`, trình biên dịch phải:

1. Tìm những phương thức có thể áp dụng.
2. Kiểm tra chuyển đổi đối số và các ràng buộc kiểu.
3. Chọn phương thức phù hợp nhất theo quy tắc độ cụ thể.

Nếu không chọn được duy nhất trong những ứng viên cùng phù hợp, lời gọi có thể bị báo **mơ hồ** (ambiguous).

Đây là lỗi lúc biên dịch, không phải tình huống JVM thử gọi từng phương thức ở runtime. Các quy tắc trong bài vẫn áp dụng trên Java hiện đại; ví dụ chạy được dùng Java 17 trở lên.

## 2. Vì sao generic làm việc đọc overload khó hơn?

Phương thức thông thường có các kiểu tham số được ghi trực tiếp, chẳng hạn `String` hoặc `long`. Phương thức generic có thể cần suy luận một hoặc nhiều tham số kiểu cho từng ứng viên.

Do đó, khi phân tích một lời gọi, không thể chỉ nhìn tên `T` rồi coi nó luôn là `Object`, cũng không thể luôn thay `T` bằng lớp thực tế của đối tượng đang chạy.

Cần phân biệt:

- **Kiểu của biểu thức ở nơi gọi:** thông tin trình biên dịch dùng khi giải quyết overload.
- **Các giới hạn của tham số kiểu:** điều kiện để một ứng viên generic được áp dụng.
- **Xóa kiểu (type erasure):** ảnh hưởng tới tính hợp lệ của tập khai báo, không phải cách duy nhất để chọn overload ở nơi gọi.
- **Lớp thực tế của đối tượng:** không tự khiến overload được chọn lại sau khi chương trình đã biên dịch.

Một mẹo dễ gây sai là “Java luôn ưu tiên phương thức không generic”. Các ví dụ cụ thể có thể chọn phương thức không generic vì nó cụ thể hơn, nhưng đó không phải quy tắc tổng quát thay thế toàn bộ quá trình.

## 3. Các giai đoạn kiểm tra khả năng áp dụng

Có thể nhớ mô hình rút gọn sau:

| Giai đoạn | Những chuyển đổi được xét |
| --- | --- |
| 1. Gọi với số đối số cố định, theo quy tắc chặt | Chưa cần boxing/unboxing và chưa dùng cơ chế gom varargs |
| 2. Gọi với số đối số cố định, theo quy tắc rộng hơn | Cho phép boxing/unboxing |
| 3. Gọi theo cơ chế varargs | Có thể gom các đối số cho tham số biến độ dài |

Chỉ chuyển sang giai đoạn sau khi giai đoạn trước không tìm được phương thức áp dụng. Sau khi có các ứng viên trong giai đoạn phù hợp, Java tiếp tục xét phương thức cụ thể nhất.

Đây là bản định hướng để đọc ví dụ, không phải toàn bộ thuật toán suy luận của JLS. Lambda, tham chiếu phương thức và các ràng buộc phức tạp có thêm quy tắc.

Một phương thức khai báo varargs cũng có thể tham gia giai đoạn đầu theo dạng nhận một mảng cố định; không nên hiểu rằng mọi phương thức có dấu `...` đều bị bỏ qua cho đến giai đoạn 3.

## 4. Ví dụ cơ bản: overload String và phương thức generic

Dùng hai phương thức `inspect` ở đầu bài:

```java
// Các câu lệnh minh họa trong một phương thức.
String text = "Java";
Object asObject = text;

String first = inspect(text);
String second = inspect(asObject);
String third = inspect(null);
```

Kết quả:

| Lời gọi | Phương thức được chọn | Lý do trong ví dụ |
| --- | --- | --- |
| `inspect(text)` | `inspect(String)` | Overload `String` cụ thể hơn ứng viên tổng quát phù hợp |
| `inspect(asObject)` | `inspect(T)` | Biểu thức đầu vào có kiểu `Object`, không tự thu hẹp thành `String` |
| `inspect(null)` | `inspect(String)` | Trong nhóm này, `String` cụ thể hơn cách nhận tổng quát |

Lớp thực tế của `asObject` vẫn là `String`, nhưng điều đó không khiến Java chọn lại `inspect(String)` khi chạy.

Bản thân `null` cũng không luôn gây mơ hồ. Nó gây vấn đề khi nhiều kiểu tham chiếu phù hợp mà không có một lựa chọn cụ thể hơn theo quy tắc áp dụng.

## 5. Boxing có thể làm thay đổi ứng viên được xét ở giai đoạn đầu

Xét:

```java
// Các phương thức minh họa trong cùng một lớp.
static String route(long value) {
    return "long";
}

static <T> String route(T value) {
    return "generic";
}
```

Hai lời gọi:

```java
// Các câu lệnh minh họa.
String fromPrimitive = route(1);
String fromWrapper = route(Integer.valueOf(1));
```

`route(1)` chọn overload `long`: `int` có thể mở rộng sang `long` mà chưa cần boxing. Ứng viên generic nhận giá trị nguyên thủy qua boxing không làm Java bỏ qua ứng viên đã áp dụng ở giai đoạn trước.

`route(Integer.valueOf(1))` chọn phương thức generic: đối số đã là tham chiếu `Integer`, có thể phù hợp với tham số kiểu mà chưa cần unboxing. Để gọi overload `long` từ `Integer`, cần unboxing rồi mở rộng giá trị nguyên thủy.

Vì vậy, đổi khai báo biến hoặc đổi một biểu thức từ `int` sang `Integer` có thể thay đổi overload được chọn. Đây là quyết định lúc biên dịch, không phải cơ chế ưu tiên theo giá trị số bên trong.

## 6. Mơ hồ do null và hai giới hạn không liên quan

Hai phương thức sau có các giới hạn khác nhau:

```java
// Các phương thức minh họa trong cùng một lớp.
static <T extends CharSequence> String classify(T value) {
    return "text";
}

static <T extends Number> String classify(T value) {
    return "number";
}
```

`CharSequence` và `Number` không có quan hệ kiểu con với nhau. Hai phương thức có thể cùng được khai báo: sau xóa kiểu, kiểu tham số tương ứng là `CharSequence` và `Number`, vẫn phân biệt được.

Lời gọi sau mơ hồ:

```java
// Minh họa lỗi; không biên dịch.
classify(null);
```

`null` phù hợp với cả hai hướng kiểu tham chiếu. Không có overload nào thắng vì một giới hạn là kiểu con của giới hạn còn lại.

Có thể làm rõ ý định bằng kiểu của đối số:

```java
// Minh họa hợp lệ.
classify((CharSequence) null);
classify((Number) null);
```

Hoặc, nếu các phương thức trên nằm trong lớp `Tools`, dùng đối số kiểu tường minh phù hợp với một giới hạn:

```java
// Minh họa hợp lệ.
Tools.<String>classify(null);
Tools.<Integer>classify(null);
```

`String` thỏa giới hạn `CharSequence` nhưng không thỏa `Number`; `Integer` thỏa giới hạn `Number` nhưng không thỏa `CharSequence`.

Các phương thức minh họa chỉ trả về nhãn, không đọc dữ liệu từ `value`, nên truyền `null` không gây lỗi runtime ở ví dụ. Trong một API thực tế, chọn được overload không đồng nghĩa dữ liệu `null` được nghiệp vụ chấp nhận.

## 7. Mơ hồ giữa hai vị trí tham số: type witness chưa chắc giải quyết được

Xét:

```java
// Các phương thức minh họa trong cùng một lớp.
static <T> String cross(T left, String right) {
    return "left-generic";
}

static <T> String cross(String left, T right) {
    return "right-generic";
}
```

Lời gọi:

```java
// Minh họa lỗi; không biên dịch.
cross("left", "right");
```

Cả hai đối số đều là `String`. Mỗi overload có một vị trí cụ thể là `String` và một vị trí do tham số kiểu nhận. Trong ví dụ này, không có một phương thức được chọn duy nhất theo quy tắc độ cụ thể.

Giả sử các phương thức nằm trong `Tools`, thêm `<Object>` vẫn không đủ:

```java
// Minh họa lỗi; vẫn mơ hồ.
Tools.<Object>cross("left", "right");
```

Hai cách nhận trở thành `(Object, String)` và `(String, Object)`; mỗi cách cụ thể hơn ở một vị trí, nhưng không thắng trên toàn bộ quan hệ cần xét.

Có thể tạo một lời gọi rõ hướng hơn bằng kiểu của biểu thức:

```java
// Minh họa hợp lệ.
cross((Object) "left", "right");
cross("left", (Object) "right");
```

Trong lời gọi đầu, overload cần `String` ở vị trí trái không còn áp dụng cho biểu thức có kiểu `Object`. Lời gọi thứ hai làm rõ theo chiều ngược lại.

Phép ép kiểu trong ví dụ là mở rộng cách nhìn từ `String` sang `Object`, nhằm minh họa chọn overload. Với API do mình thiết kế, các tên riêng như `combineLeft` và `combineRight` có thể truyền đạt ý định tốt hơn việc bắt mọi người gọi ghi nhớ những phép ép kiểu để phân giải.

## 8. Đối số kiểu tường minh không luôn buộc chọn overload generic

Quay lại nhóm `inspect(T)` và `inspect(String)`.

Trong Java, một phương thức không generic vẫn có thể được chọn từ một lời gọi cung cấp danh sách đối số kiểu; khi điều đó xảy ra, danh sách kiểu ấy bị bỏ qua theo quy tắc ngôn ngữ.

Vì vậy, nếu các phương thức nằm trong `Tools`:

```java
// Minh họa hợp lệ với nhóm inspect đã khai báo.
String selected = Tools.<Object>inspect("Java");
```

Lời gọi này vẫn chọn `inspect(String)` trong ví dụ. Không thể dùng quy tắc “đã viết `<Object>` thì chắc chắn chọn `inspect(T)`”.

Muốn kiểm tra overload thực sự được chọn, đọc toàn bộ tập chữ ký và kiểu đối số hoặc dùng thông tin của IDE. Không chỉ nhìn thấy dấu `<...>` ở nơi gọi rồi kết luận phương thức đích là generic.

## 9. Lỗi khai báo do xóa kiểu khác với lỗi lời gọi mơ hồ

Hai phương thức sau không tạo thành một nhóm overload hợp lệ:

```java
// Minh họa lỗi khai báo; không biên dịch.
static <T> void store(T value) {
}

static void store(Object value) {
}
```

Tham số `T` không có giới hạn tường minh được xóa thành `Object`. Hai khai báo xung đột ngay trong lớp; không cần có một lời gọi `store(...)` mới phát sinh lỗi.

Tương tự, chỉ khác đối số kiểu như `read(List<String>)` và `read(List<Integer>)` không tạo được hai overload riêng trong cùng lớp, vì cả hai danh sách tham số đều bị xóa về `List`.

Đổi tên `T` thành `U` cũng không tạo một chữ ký mới. Chỉ khác kiểu trả về không đủ để nạp chồng; kiểu biến nhận kết quả không cứu được hai khai báo vốn trùng/xung đột.

Cần phân biệt ba loại vấn đề:

| Vấn đề | Xảy ra ở đâu? | Ví dụ |
| --- | --- | --- |
| Xung đột khai báo | Ngay khi khai báo lớp/phương thức | `store(T)` và `store(Object)` như trên |
| Không có phương thức áp dụng | Khi phân tích lời gọi | Mọi ứng viên đều không thỏa kiểu/giới hạn |
| Lời gọi mơ hồ | Khi phân tích lời gọi | Nhiều ứng viên áp dụng nhưng không chọn được phương thức thích hợp duy nhất trong ví dụ |

Không nên sửa mọi lỗi bằng cách thêm đối số kiểu tường minh. Với xung đột khai báo, cần đổi thiết kế các phương thức trước.

## 10. Chương trình đầy đủ

Lưu vào `GenericOverloadDemo.java`:

```java
public class GenericOverloadDemo {
    static <T> String inspect(T value) {
        return "generic";
    }

    static String inspect(String value) {
        return "String";
    }

    static String route(long value) {
        return "long";
    }

    static <T> String route(T value) {
        return "generic";
    }

    static <T extends CharSequence> String classify(T value) {
        return "text";
    }

    static <T extends Number> String classify(T value) {
        return "number";
    }

    static <T> String cross(T left, String right) {
        return "left-generic";
    }

    static <T> String cross(String left, T right) {
        return "right-generic";
    }

    public static void main(String[] args) {
        System.out.println(inspect("Java"));

        Object asObject = "Java";
        System.out.println(inspect(asObject));
        System.out.println(inspect(null));

        System.out.println(route(1));
        System.out.println(route(Integer.valueOf(1)));

        System.out.println(classify((CharSequence) null));
        System.out.println(GenericOverloadDemo.<String>classify(null));
        System.out.println(GenericOverloadDemo.<Integer>classify(null));

        System.out.println(cross((Object) "left", "right"));
        System.out.println(cross("left", (Object) "right"));

        System.out.println(GenericOverloadDemo.<Object>inspect("Java"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 GenericOverloadDemo.java
java GenericOverloadDemo
```

Stdout chính xác:

```text
String
generic
String
long
generic
text
text
number
left-generic
right-generic
String
```

Chương trình chỉ chứa các lời gọi đã phân giải rõ. Các phương thức trả nhãn để nhìn thấy lựa chọn của trình biên dịch; chúng không dùng nhãn đó như một thuật toán xử lý dữ liệu thực tế.

### Thử riêng các lời gọi cố ý mơ hồ

Giữ `GenericOverloadDemo.java` như trên và tạo thêm `AmbiguousCalls.java`:

```java
public class AmbiguousCalls {
    void test() {
        GenericOverloadDemo.classify(null);
        GenericOverloadDemo.cross("left", "right");
        GenericOverloadDemo.<Object>cross("left", "right");
    }
}
```

Biên dịch tệp này sau khi đã biên dịch chương trình chính:

```shell
javac --release 17 -encoding UTF-8 AmbiguousCalls.java
```

Tệp cố ý không biên dịch: cả ba lời gọi đều mơ hồ. Không có stdout để so sánh, vì chương trình chưa được tạo thành mã có thể chạy. Câu chữ chẩn đoán có thể khác giữa các phiên bản `javac`; điều cần quan sát là từng lời gọi bị từ chối vì có các ứng viên cạnh tranh.

## 11. Quy trình phân tích và sửa lỗi

1. **Kiểm tra tập khai báo có hợp lệ không.** Nếu có lỗi trùng/xung đột sau xóa kiểu, xử lý ở phần khai báo trước.
2. **Ghi kiểu của từng biểu thức đối số.** Ví dụ `Object x = "Java"` cung cấp biểu thức kiểu `Object` khi truyền `x`.
3. **Liệt kê các ứng viên và giới hạn kiểu.** Với mỗi ứng viên generic, xem có lựa chọn đối số kiểu nào hợp lệ.
4. **Xem giai đoạn áp dụng.** Đừng so độ cụ thể giữa mọi ứng viên trước khi xét boxing/unboxing và varargs.
5. **So sánh độ cụ thể.** Nếu một ứng viên tốt hơn ở vị trí này nhưng kém hơn ở vị trí khác, cần kiểm tra khả năng mơ hồ.
6. **Làm rõ ý định ở nơi gọi khi phù hợp.** Dùng biến có kiểu rõ, phép chuyển kiểu an toàn hoặc type witness thực sự loại được ứng viên không mong muốn.
7. **Sửa API nếu việc gọi quá khó hiểu.** Đổi tên theo ý nghĩa, gom dữ liệu vào một kiểu miền rõ ràng hoặc giảm các overload chồng lấn.

Không thêm một overload rất rộng rồi dựa vào may mắn để nó đóng vai trò “fallback”. Một overload mới có thể khiến mã nguồn đang biên dịch được trở nên mơ hồ hoặc chọn một phương thức khác sau khi biên dịch lại.

## 12. Tự kiểm tra

- Vì sao `inspect((Object) "Java")` không chọn overload `String`, dù đối tượng vẫn là chuỗi?
- Vì sao `route(1)` và `route(Integer.valueOf(1))` đi vào hai overload khác nhau?
- Vì sao `inspect(null)` hợp lệ nhưng `classify(null)` mơ hồ trong các nhóm khai báo của bài?
- Thử dùng `<Object>` cho `cross("left", "right")`. Giải thích vì sao hai ứng viên vẫn cạnh tranh.
- So sánh lỗi của `AmbiguousCalls` với lỗi khi đặt `store(T)` và `store(Object)` trong cùng một lớp.
- Đề xuất tên riêng cho hai overload `cross` để người gọi không cần ép kiểu chỉ nhằm chọn phương thức.
- Nếu thêm một overload mới vào thư viện, vì sao cần kiểm tra lại các lời gọi hiện có sau khi biên dịch lại?

## Tài liệu đối chiếu

- [Java Language Specification — Overloading (§8.4.9)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.9): nhóm phương thức nạp chồng.
- [Java Language Specification — Method Signature (§8.4.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.2): chữ ký và các khai báo tương đương/xung đột.
- [Java Language Specification — Determine Method Signature (§15.12.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2): các giai đoạn kiểm tra khả năng áp dụng.
- [Java Language Specification — Choosing the Most Specific Method (§15.12.2.5)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2.5): chọn phương thức cụ thể nhất và lời gọi mơ hồ.
