# Phép chiếu kiểu lên trên và loại bỏ biến kiểu tổng hợp khi suy luận `var`

**Chủ đề:** Kiểu suy luận nâng cao — Java 10 trở lên.

Trong một số biểu thức sử dụng generics và wildcard, trình biên dịch phải tạo **biến kiểu tổng hợp** (*synthetic type variable*) để tính kiểu trung gian. Khi khai báo biến cục bộ bằng `var`, Java không cho các biến kiểu nội bộ đó trở thành thành phần tồn tại lâu dài của kiểu biến cục bộ. Thay vào đó, ngôn ngữ áp dụng **phép chiếu kiểu lên trên** (*upward projection*) để chọn một kiểu cha phù hợp, không còn chứa các biến kiểu tổng hợp cần loại bỏ.

Đây là quy tắc của Java Language Specification (JLS `14.4.1 và `4.10.5), được áp dụng từ khi `var` cho biến cục bộ xuất hiện ở Java 10 và vẫn có hiệu lực trong Java hiện đại. Bài học tập trung vào cơ chế này, các giới hạn an toàn kiểu, và cách xử lý khi cần giữ thông tin generic cụ thể.

## 1. Vì sao có biến kiểu tổng hợp?

Xét một danh sách có kiểu:

~~~java
List<? extends Number> numbers = List.of(2, 4);
~~~

`? extends Number` diễn tả rằng phần tử thuộc **một kiểu chưa biết nhưng là kiểu con của `Number`**. Tại một số thao tác generic, trình biên dịch thực hiện *capture conversion*: thay wildcard bằng một biến kiểu nội bộ tạm thời để kiểm tra tính hợp lệ của phép gọi.

Ví dụ phương thức generic:

~~~java
static <T> List<T> identity(List<T> items) {
    return items;
}
~~~

Khi gọi `identity(numbers)`, trình biên dịch cần xử lý `T` tương ứng với kiểu phần tử chưa biết của `numbers`. Ta có thể hình dung một kiểu tạm như:

~~~text
List<? extends Number>
        |
        | capture conversion trong quá trình kiểm tra lời gọi
        v
List<CAP#1>          // kiểu trung gian minh họa
        |
        | upward projection khi khai báo var
        v
List<? extends Number>  // kiểu có thể giữ an toàn sau khai báo
~~~

`CAP#1` chỉ là ký hiệu **minh họa** thường gặp trong thông báo lỗi của `javac`; tên, số thứ tự và cách hiển thị là chi tiết của trình biên dịch. Người lập trình không thể viết `CAP#1` như một kiểu trong mã Java.

**Biến kiểu tổng hợp khác với:**

- `T` do người viết khai báo trong `<T>` của một lớp hoặc phương thức generic: đó là **type parameter được khai báo trong mã nguồn**, không phải tự nó là một biến kiểu tổng hợp.
- Một biến giá trị như `var number = 2;`: biến này chứa giá trị dữ liệu; `CAP#1` là đại diện kiểu nội bộ phục vụ kiểm tra lúc biên dịch.
- Kiểu `Object` hoặc kiểu raw: loại bỏ biến kiểu tổng hợp **không có nghĩa** xóa toàn bộ thông tin generic.
- Thành phần synthetic trong bytecode hay reflection: chủ đề ở đây là **phép suy luận kiểu trong ngôn ngữ Java**.

Biến kiểu tổng hợp có thể xuất hiện trong quá trình *capture conversion* (`JLS 5.1.10`) hoặc trong một số trường hợp giải các biến suy luận kiểu (`JLS 18.4`). Phép chiếu giúp các biến kiểu này không vượt phạm vi biểu thức đã tạo ra chúng.

## 2. Quy tắc của `var`: suy luận rồi chiếu lên trên

Với khai báo biến cục bộ thông thường:

~~~java
var result = expression;
~~~

Java xác định kiểu `T` của `expression` như một **biểu thức độc lập** (*standalone expression*, không lấy `var` làm target type). Sau đó kiểu của `result` là:

~~~text
upwardProjection(T, các biến kiểu tổng hợp được nhắc đến trong T)
~~~

Diễn giải hữu ích:

1. **Không có biến kiểu tổng hợp cần loại bỏ:** phép chiếu trả về chính kiểu `T`; không có lý do để làm rộng kiểu.
2. **`T` chính là một biến kiểu tổng hợp:** phép chiếu dựa vào **giới hạn trên** (*upper bound*) của biến đó; giới hạn có thể là `Number`, `Object` hoặc kiểu phức tạp khác.
3. **Biến kiểu tổng hợp nằm trong đối số generic**, chẳng hạn `List<CAP#1>`: trình biên dịch xây dựng một kiểu generic tương thích có đối số wildcard, ví dụ `List<? extends Number>`. Trong trường hợp thích hợp, kết quả có thể là `? super L` hoặc `?`.
4. **Có cấu trúc lồng nhau** (`List<List<...>>`), mảng hoặc intersection type: quy tắc được áp dụng đệ quy theo cấu trúc kiểu.

JLS `4.10.5 định nghĩa đầy đủ các trường hợp, kể cả phép *downward projection* phụ trợ để xác định lower bound. Vì vậy không có một công thức đơn giản dạng “mọi `CAP` đều thành `Object`” hoặc “mọi `CAP` đều thành `? extends`”.

**Mục đích:** chọn kiểu đủ rộng để không chứa biến kiểu tổng hợp bị hạn chế, nhưng vẫn giữ được các ràng buộc an toàn mà chương trình có thể sử dụng. `var` vẫn có **kiểu tĩnh được chốt tại thời điểm biên dịch**.

### Phép chiếu lên trên không phải ép kiểu lúc chạy

Không có đối tượng mới được tạo ra chỉ vì upward projection. Phương thức `identity` vẫn trả về đúng danh sách được truyền vào. Cơ chế này diễn ra khi **phân tích kiểu ở thời điểm biên dịch**, không thay đổi nội dung collection hay thông tin generic thực tế tại runtime.

## 3. Trường hợp 1 — Wildcard có giới hạn trên (`? extends`)

Giả sử:

~~~java
List<? extends Number> numbers = List.of(2, 4);
var projected = identity(numbers);
~~~

Trong quá trình suy luận kiểu cho lời gọi `identity(numbers)`, trình biên dịch có thể cần một biến capture tạm có upper bound `Number`. Khi kiểu kết quả được gắn cho `projected` qua `var`, upward projection loại bỏ capture đó mà **giữ ràng buộc `? extends Number`**.

Do đó, mã dưới đây hợp lệ:

~~~java
List<? extends Number> view = projected;
Number firstNumber = projected.get(0);
~~~

`projected.get(0)` có thể đọc an toàn dưới kiểu `Number`, vì mọi phần tử trong danh sách đều là một kiểu con nào đó của `Number`.

Tuy nhiên:

~~~java
// projected.add(9);                  // LỖI biên dịch
// List<Number> exact = projected;     // LỖI biên dịch
~~~

Hai dòng trên là **đoạn minh họa lỗi**, không được bật trong chương trình chạy:

- `add(9)` không được phép vì không biết kiểu phần tử chính xác là `Integer`, `Double` hay kiểu con khác của `Number`. Thêm một `Integer` vào danh sách có phần tử chỉ nhận `Double` sẽ không an toàn.
- `List<? extends Number>` không phải `List<Number>`. Generics trong Java bất biến về đối số kiểu; không có phép chuyển đổi ngầm như trên.

**Lưu ý về thông báo lỗi:** ngay cả sau khi biến `var` đã có kiểu được chiếu, `javac` vẫn có thể hiện `CAP#1` trong chẩn đoán tại một biểu thức sử dụng wildcard sau đó. Đó có thể là một *capture conversion mới* để kiểm tra biểu thức ấy; không chứng tỏ biến kiểu tổng hợp từ initializer đã bị giữ lại trong khai báo `var`.

## 4. Trường hợp 2 — Kiểu kết quả là chính biến capture

Một phương thức generic trả về một phần tử:

~~~java
static <T> T first(List<T> items) {
    return items.get(0);
}
~~~

Với:

~~~java
List<? extends Number> numbers = List.of(2, 4);
var head = first(numbers);
Number value = head;  // hợp lệ
// Integer exact = head; // LỖI: head có kiểu Number
~~~

Ở lời gọi `first(numbers)`, kiểu trung gian có thể là capture của `? extends Number`. Vì bản thân kết quả là biến kiểu bị giới hạn, **upward projection chọn upper bound `Number`** cho khai báo `head`.

Điều này không có nghĩa giá trị bên trong bị biến thành một đối tượng `Number` mới. Giá trị vẫn là đối tượng thực tế của danh sách (ở đây là `Integer`); chỉ **kiểu tĩnh** của `head` không hứa rằng nó luôn là `Integer`.

Đừng dùng ép kiểu xuống `Integer` chỉ để né lỗi nếu API thực sự chấp nhận nhiều lớp con của `Number`. Khi cần `Integer` chính xác, hãy đặt hợp đồng kiểu rõ ngay từ đầu, ví dụ `List<Integer>` hoặc phương thức nhận đúng `List<Integer>`.

## 5. Trường hợp 3 — Wildcard giới hạn dưới (`? super`)

Với:

~~~java
List<? super Integer> target = new ArrayList<Number>();
var lower = identity(target);
List<? super Integer> view = lower;
view.add(7);
Object stored = lower.get(0);
~~~

Khi capture wildcard `? super Integer`, biến nội bộ có **lower bound** `Integer` và upper bound tương ứng. Phép chiếu có thể bảo toàn hướng ràng buộc bằng kiểu có wildcard **`? super Integer`**, thay vì biến mọi thông tin thành `Object`.

Ở đây:

- Ghi `Integer` bằng `add(7)` là an toàn: danh sách chấp nhận `Integer` hoặc một kiểu cha của nó.
- Đọc một phần tử chỉ có thể nhận chắc chắn dưới kiểu `Object`. Chẳng hạn, `Number n = lower.get(0);` không được bảo đảm hợp lệ với mọi danh sách `List<? super Integer>`.
- Không thể gán một `List<? super Integer>` cho `List<Integer>` hoặc `List<Number>` nếu không có bằng chứng kiểu cụ thể.

Đó là sự khác nhau giữa **producer (`extends`)** và **consumer (`super`)** khi thao tác với wildcard. Phép chiếu phải giữ giới hạn theo hướng phù hợp để bảo vệ an toàn kiểu.

## 6. Trường hợp 4 — Kiểu generic lồng nhau và trường hợp không cần chiếu

Một phương thức bao gói danh sách thành danh sách hai tầng:

~~~java
static <T> List<List<T>> wrap(List<T> items) {
    return List.of(items);
}
~~~

Có thể dùng kết quả với wildcard lồng:

~~~java
List<? extends Number> numbers = List.of(2, 4);
var nested = wrap(numbers);
List<? extends List<? extends Number>> safeView = nested;
Number second = safeView.get(0).get(1);
~~~

Chữ ký `wrap` kết hợp với wildcard ở `numbers` có thể tạo kiểu trung gian chứa capture ở tầng trong. Phép chiếu đưa biến `nested` tới kiểu có thể dùng an toàn mà **không cho capture nội bộ thoát ra thành tên kiểu ở câu lệnh kế tiếp**. Việc gán cho `safeView` và đọc ra `Number` đều hợp lệ.

Ngược lại, không phải mọi `var` đều cần thay đổi kiểu:

~~~java
var texts = List.of("A", "B"); // kiểu List<String>
String value = texts.get(0);  // hợp lệ
~~~

Không có biến kiểu tổng hợp bị hạn chế nào cần chiếu ở kết quả `List<String>` này, nên kiểu được giữ nguyên. Dùng `var` không tự làm rộng `List<String>` thành `List<?>` hoặc `List<Object>`.

### Kiểu không có tên trong mã nguồn không đồng nghĩa với biến kiểu tổng hợp

Java cho phép `var` giữ kiểu **anonymous class** của một initializer, ví dụ:

~~~java
var local = new Object() {
    String label() { return "anonymous"; }
};
System.out.println(local.label()); // hợp lệ, có thể gọi method của anonymous class
~~~

Kiểu anonymous class không có tên tường minh để viết trong khai báo Java, nhưng nó **không tự động bị chiếu thành `Object`** vì quy tắc chỉ loại bỏ **các biến kiểu tổng hợp thuộc tập bị hạn chế**. Bản thân việc “không viết được tên kiểu” không phải tiêu chí để bỏ toàn bộ thông tin kiểu.

## 7. Ví dụ độc lập chạy được với Java 10 trở lên

Lưu chương trình sau với tên chính xác **`UpwardProjectionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class UpwardProjectionDemo {
    static <T> List<T> identity(List<T> items) {
        return items;
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    static <T> List<List<T>> wrap(List<T> items) {
        return List.of(items);
    }

    public static void main(String[] args) {
        List<? extends Number> source = List.of(2, 4);
        var upper = identity(source);
        List<? extends Number> upperView = upper;
        Number number = upper.get(0);
        System.out.println("upper=" + number);
        System.out.println("size=" + upperView.size());

        var head = first(source);
        Number headAsNumber = head;
        System.out.println("head=" + headAsNumber);

        var nested = wrap(source);
        List<? extends List<? extends Number>> nestedView = nested;
        Number second = nestedView.get(0).get(1);
        System.out.println("nested=" + second);

        List<? super Integer> target = new ArrayList<Number>();
        var lower = identity(target);
        List<? super Integer> lowerView = lower;
        lowerView.add(7);
        Object stored = lower.get(0);
        System.out.println("lower=" + stored);

        var plain = List.of("A", "B");
        String text = plain.get(0);
        System.out.println("plain=" + text);

        var anonymous = new Object() {
            String label() { return "anonymous"; }
        };
        System.out.println("anon=" + anonymous.label());
    }
}
~~~

Biên dịch với cú pháp Java 10 bằng JDK hiện đại có hỗ trợ `--release 10`, sau đó chạy:

~~~bash
javac --release 10 UpwardProjectionDemo.java
java UpwardProjectionDemo
~~~

**Stdout chính xác:**

~~~text
upper=2
size=2
head=2
nested=4
lower=7
plain=A
anon=anonymous
~~~

Giải thích kết quả:

1. `upper` và `upperView` giữ an toàn giới hạn trên: đọc được phần tử như `Number`.
2. `head` được dùng như `Number` khi kết quả của phương thức generic trả về một giá trị capture.
3. `nestedView` chứng minh wildcard lồng nhau vẫn cho phép đọc dữ liệu theo giới hạn `Number`.
4. `lower` nhận một danh sách có kiểu phần tử thuộc vùng `? super Integer`; thêm `Integer` được, đọc lại phải dùng kiểu bảo đảm `Object`.
5. `plain` là ví dụ suy luận thông thường không cần loại bỏ biến kiểu tổng hợp; `anonymous` minh họa kiểu anonymous class vẫn giữ được thành viên `label()`.

Đây là chương trình thực thi đầy đủ, không phụ thuộc mã hay tệp khác. `List.of` có mặt từ Java 9, `var` từ Java 10, nên các thành phần đều tương thích với nguồn Java 10.

## 8. Các tình huống lỗi biên dịch để đối chiếu

Các dòng gây lỗi dưới đây **chỉ là ví dụ kiểm tra kiểu**, không phải mã chạy độc lập:

~~~java
List<? extends Number> input = List.of(2, 4);
var upper = identity(input);

// upper.add(9);               // KHÔNG HỢP LỆ: kiểu phần tử cụ thể chưa biết
// List<Number> exact = upper;  // KHÔNG HỢP LỆ: wildcard khác Number tường minh

var head = first(input);
// Integer exactHead = head;   // KHÔNG HỢP LỆ: kiểu tĩnh của head là Number
~~~

Lỗi ở `add(9)` và `List<Number> exact = upper` là hệ quả trực tiếp của ràng buộc wildcard; lỗi ở `Integer exactHead = head` phát sinh vì `Number` không tự chuyển về `Integer`. Khi cần kiểu chính xác, sửa **hợp đồng generic** hoặc cách khai báo ban đầu. Không dùng raw type hay unchecked cast để che mất kiểm tra của trình biên dịch.

**Phân biệt lỗi bản chất với thông báo `CAP#1`:** thông báo của `javac` có thể liệt kê một capture mới tại vị trí kiểm tra `add` hoặc phép gán. Điều cần hiểu là kiểu công khai có thể sử dụng của biến vẫn không được phép bỏ qua wildcard và giới hạn của nó; không nên dựa vào tên `CAP#n` làm API.

## 9. Phân biệt với các khái niệm dễ nhầm

| Khái niệm | Vai trò | Có phải upward projection trong `var`? |
| --- | --- | --- |
| *Capture conversion* | Tạo biến kiểu nội bộ để xử lý wildcard khi kiểm tra generic | Là một **nguồn** sinh biến kiểu cần chiếu, không đồng nghĩa với phép chiếu |
| *Inference variable resolution* | Giải ràng buộc của quá trình suy luận generic; đôi khi tạo biến kiểu mới | Có thể tạo biến kiểu tổng hợp cần loại bỏ |
| *Upward projection* | Tạo kiểu cha phù hợp không còn chứa biến kiểu tổng hợp bị hạn chế | **Đúng**, là quy tắc xác định kiểu biến cục bộ `var` |
| *Downward projection* | Phép phụ trợ tìm kiểu con phù hợp trong những trường hợp có thể; dùng khi xác định một số wildcard lower bound | Không phải kết quả chung của `var`; được dùng bên trong thuật toán phép chiếu |
| *Type erasure* | Cơ chế biên dịch generic để biểu diễn phần lớn thông tin kiểu tại runtime | **Khác**: upward projection là bước kiểm tra kiểu tĩnh, không phải việc bỏ generic khi tạo bytecode |
| *Widening conversion* như `int -> long` | Chuyển đổi kiểu giá trị theo ngữ cảnh biểu thức | **Khác** với phép chiếu kiểu liên quan capture wildcard |
| `var` với anonymous class | Có thể giữ kiểu không có tên khai báo tường minh | Không mặc định làm mất các phương thức của anonymous class |
| `var x = new ArrayList<>()` | Suy luận kiểu đối số generic theo ràng buộc tại initializer | Có thể dẫn đến `ArrayList<Object>` nếu thiếu thông tin kiểu; **không có nghĩa** luôn cần chiếu biến capture |

Nếu `var list = new ArrayList<>();` suy luận ra `ArrayList<Object>`, đó là bài toán **thiếu thông tin suy luận type argument** của diamond. Nó khác với tình huống `identity(List<? extends Number>)`, nơi compiler tạo capture và phải chiếu để không cho biến kiểu tổng hợp thoát ra phạm vi câu lệnh.

## 10. Cách áp dụng trong dự án thực tế

- Khi một biểu thức trả về generic có wildcard, đừng giả định `var` sẽ giữ lại một kiểu tham số cụ thể như `List<Integer>`. Hãy đọc chữ ký phương thức và xét `extends`/`super`.
- Nếu chủ yếu **đọc** giá trị từ `List<? extends Number>`, dùng kiểu `Number` hoặc giao diện có ràng buộc tương ứng; tránh ép xuống `Integer` khi không có bảo đảm.
- Nếu chủ yếu **thêm** giá trị vào `List<? super Integer>`, thêm `Integer` là an toàn; khi đọc, chỉ bảo đảm `Object`.
- Khi API cần kiểu chính xác, cân nhắc viết kiểu tường minh như `List<Integer> result = ...` hoặc điều chỉnh nguồn dữ liệu và phương thức generic để truyền đúng thông tin kiểu.
- Nếu thông báo lỗi có `CAP#n`, hiểu đây là dấu hiệu trình biên dịch đang xử lý wildcard bằng capture conversion. Xem lại ràng buộc, đừng cố đặt tên hay tham chiếu trực tiếp `CAP#n`.
- Để quan sát **kiểu tĩnh**, hãy dùng các phép gán/method call mà trình biên dịch kiểm tra hoặc tính năng hiển thị kiểu của IDE. Gọi `getClass()` không thể cho biết wildcard và đối số generic đầy đủ, do type erasure.

Không cần gọi thủ công hàm “upward projection” nào trong Java: đây là một phần của ngôn ngữ. Mục tiêu khi viết mã là cung cấp generic contract rõ ràng, biết các thao tác nào an toàn và hiểu tại sao một phép gán bị từ chối.

## 11. Tự kiểm tra

1. `CAP#1` trong lỗi generic là tên kiểu do người lập trình khai báo hay một ký hiệu nội bộ?
2. Vì sao `var upper = identity(numbers);` với `numbers` kiểu `List<? extends Number>` cho phép đọc `Number` nhưng không cho `upper.add(9)`?
3. Với `var head = first(numbers);`, vì sao phép gán cho `Number` hợp lệ nhưng gán trực tiếp cho `Integer` có thể sai?
4. Với `List<? super Integer> target`, thao tác nào bảo đảm an toàn: `target.add(7)`, `Number n = target.get(0)` hay `Object x = target.get(0)`?
5. Vì sao `var obj = new Object() { String label(){ return "ok"; } };` vẫn có thể gọi `obj.label()`?
6. Phép chiếu lên trên có đồng nghĩa với type erasure hoặc chuyển toàn bộ kiểu thành `Object` không?

**Đáp án:** (1) ký hiệu trình biên dịch dùng cho biến kiểu capture tổng hợp; (2) giữ giới hạn trên `Number` nhưng không biết lớp con chính xác; (3) kiểu tĩnh sau projection đủ bảo đảm `Number`, không hứa `Integer`; (4) `add(7)` và đọc bằng `Object`; (5) kiểu anonymous class vẫn được giữ vì không có biến kiểu tổng hợp cần loại bỏ theo quy tắc này; (6) không, phép chiếu bảo toàn ràng buộc kiểu cần thiết khi có thể và diễn ra lúc biên dịch.

## 12. Tham chiếu đặc tả

- **Java Language Specification `14.4.1 — Local Variable Declarators and Types:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1
- **Java Language Specification `4.10.5 — Type Projections:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.5
- **Java Language Specification `5.1.10 — Capture Conversion:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10

Các quy tắc trên là quy tắc kiểu của Java hiện hành, không phải một kỹ thuật riêng cho JDK cũ hoặc một API đã bị loại bỏ.