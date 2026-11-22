# Vì sao dùng `Object` và ép kiểu dễ để lỗi đến lúc chạy?

Trong Java, `Object` là lớp cha của mọi **kiểu tham chiếu**. Vì thế, một biến `Object` có thể trỏ tới một đối tượng `String`, `Integer`, `Customer` hoặc nhiều loại đối tượng khác. Điều này có vẻ linh hoạt, nhưng nếu chương trình phải **ép kiểu xuống** (`downcast`) liên tục để dùng dữ liệu, sự linh hoạt ấy có thể làm mất thông tin kiểu tại nơi biên dịch và đẩy lỗi sang lúc chạy.

Bài này giải thích chính xác vì sao `Object` cùng ép kiểu có rủi ro, `ClassCastException` xuất hiện ở đâu, Java Generics giảm rủi ro đó thế nào và những trường hợp nào vẫn cần kiểm tra kiểu.

## 1. `Object` cho phép giữ nhiều loại đối tượng, nhưng không nói rõ loại mong đợi

Ví dụ:

```java
Object value = "Java";          // Đối tượng thực tế là String
value = Integer.valueOf(42);   // Đối tượng thực tế là Integer
```

Cả hai phép gán đều hợp lệ: `String` và `Integer` là các kiểu tham chiếu, nên đều có thể gán cho `Object`. Tuy nhiên, **kiểu tĩnh của biến** `value` vẫn là `Object`. Trình biên dịch chỉ cho phép gọi trực tiếp những phương thức có trong API của `Object`, chẳng hạn `toString()`; nó không thể suy luận rằng `value` chắc chắn có phương thức `toUpperCase()` của `String`.

Phải phân biệt hai khái niệm:

| Khái niệm | Trong `Object value = "Java";` | Ý nghĩa |
|---|---|---|
| Kiểu tĩnh (`compile-time type`) | `Object` | Trình biên dịch dựa vào đây để kiểm tra thao tác hợp lệ. |
| Kiểu thực tế lúc chạy (`runtime type`) | `String` | JVM dựa vào đối tượng thực tế để kiểm tra ép kiểu và thực thi phương thức. |

Nếu chỉ nhìn vào kiểu `Object`, người đọc API không biết dữ liệu thuộc kiểu gì và thường phải tìm thêm tài liệu, kiểm tra điều kiện hoặc ép kiểu để dùng đúng.

> `Object` tự thân không gây lỗi. Rủi ro xuất hiện khi chương trình **giả định** một giá trị kiểu `Object` chắc chắn có kiểu cụ thể, nhưng giả định ấy không được bảo đảm.

## 2. Vì sao ép kiểu vẫn biên dịch được nhưng có thể lỗi khi chạy?

Xem phép ép kiểu:

```java
Object value = Integer.valueOf(42);
String text = (String) value;
```

Biểu thức `(String) value` là một phép ép kiểu tường minh (`explicit cast`). Vì kiểu tĩnh của `value` là `Object`, trình biên dịch cho phép yêu cầu kiểm tra nó có phải `String` hay không. **Cho phép biên dịch không đồng nghĩa với xác nhận ép kiểu sẽ thành công**.

Khi chạy, JVM kiểm tra đối tượng thực tế. `value` đang tham chiếu tới một `Integer`, không phải `String`, vì vậy phép ép kiểu ném `ClassCastException`. Nếu không được bắt, ngoại lệ làm luồng thực thi hiện tại kết thúc bất thường.

Cơ chế theo thứ tự:

1. Giá trị `Integer(42)` được gán vào biến có kiểu tĩnh `Object`.
2. Trình biên dịch thấy một phép chuyển từ `Object` xuống `String` có thể hợp lệ về mặt cú pháp và quan hệ kiểu.
3. Khi thực thi phép ép, JVM kiểm tra đối tượng được tham chiếu có tương thích với `String` hay không.
4. Đối tượng là `Integer`, nên kiểm tra thất bại và JVM ném `ClassCastException` ngay tại phép ép.

Không phải **mọi** phép ép sai đều đợi đến lúc chạy: nếu trình biên dịch đã biết hai kiểu không thể chuyển đổi hợp lệ, nó có thể báo lỗi ngay khi biên dịch. Vấn đề nổi bật ở đây là thông tin kiểu bị che bớt sau `Object` nên trình biên dịch chưa đủ cơ sở bác bỏ phép ép.

### Ví dụ hoàn chỉnh: lỗi chỉ xuất hiện với phần tử thứ hai

Lưu thành `ObjectCastDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ObjectCastDemo {
    public static void main(String[] args) {
        List<Object> values = new ArrayList<>();
        values.add("Java");
        values.add(42);

        for (Object value : values) {
            try {
                String word = (String) value;
                System.out.println(word.toUpperCase());
            } catch (ClassCastException ex) {
                System.out.println(
                    "Không thể ép " + value.getClass().getSimpleName() + " thành String"
                );
            }
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 ObjectCastDemo.java
java ObjectCastDemo
```

`stdout`:

```text
JAVA
Không thể ép Integer thành String
```

`List<Object>` ở đây **vẫn là một kiểu generic**, nhưng tham số kiểu là `Object`. Do đó danh sách được phép nhận cả chuỗi lẫn số nguyên. Vòng lặp giả định tất cả phần tử là `String`. Phần tử đầu phù hợp nên chạy tốt; phần tử thứ hai không phù hợp nên ném ngoại lệ.

Điều nguy hiểm trong thực tế là lỗi có thể nằm rất xa nơi dữ liệu được thêm vào: một thành phần lưu giá trị `Object`, thành phần khác đọc ra và ép kiểu, trong khi bộ test chỉ tình cờ dùng dữ liệu cùng kiểu.

## 3. Ba nguyên nhân khiến lỗi bị trì hoãn

**Mất ràng buộc kiểu của hợp đồng dữ liệu.** Một API trả về `Object` không thể diễn đạt rõ với trình biên dịch rằng “giá trị này phải là `String`”. Người gọi phải dựa vào quy ước, tài liệu hoặc giả định.

**Ép kiểu tường minh chỉ là yêu cầu kiểm tra.** Cú pháp `(String) value` không biến một `Integer` thành chuỗi và không bảo đảm dữ liệu đầu vào đúng kiểu. Ép kiểu tham chiếu khác với chuyển đổi dữ liệu; muốn chuyển một số thành biểu diễn chuỗi, có thể dùng `String.valueOf(42)`, với ngữ nghĩa khác hẳn.

**Dữ liệu có thể thay đổi theo nhánh chạy.** Một nhánh thêm `String`, nhánh khác thêm `Integer`, hay một giá trị đến từ plugin, cache hoặc dữ liệu bên ngoài. Đường chạy thông thường có thể thành công rất lâu trước khi nhánh sai kiểu được kích hoạt.

Phân biệt các lỗi thường gặp:

| Tình huống | Kết quả |
|---|---|
| Ép một đối tượng `Integer` sang `String` thông qua biến `Object` | `ClassCastException` tại lúc chạy. |
| Ép `null` sang `String` | Bản thân phép ép cho kết quả `null`; gọi phương thức trên `null` mới gây `NullPointerException`. |
| Gọi `value.toUpperCase()` khi `value` có kiểu tĩnh `Object` | Lỗi biên dịch vì `Object` không khai báo phương thức đó. |
| Dùng `String.valueOf(value)` | Chuyển sang biểu diễn chuỗi; không phải phép ép đối tượng thành `String`. |

## 4. Generics đưa kiểm tra kiểu về thời điểm biên dịch

Thay vì chỉ mô tả một hộp chứa `Object`, ta đặt **tham số kiểu** `T` để mô tả dữ liệu được chứa và được trả ra:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

public class GenericBoxDemo {
    public static void main(String[] args) {
        Box<String> labelBox = new Box<>("Java");
        System.out.println(labelBox.get().toUpperCase());

        Box<Integer> yearBox = new Box<>(2026);
        System.out.println(yearBox.get() + 1);
    }
}
```

Lưu thành `GenericBoxDemo.java`, sau đó chạy:

```bash
javac -encoding UTF-8 GenericBoxDemo.java
java GenericBoxDemo
```

`stdout`:

```text
JAVA
2027
```

Trong `Box<String>`, trình biên dịch biết `get()` cho ra một `String` theo hợp đồng kiểu; người gọi không cần tự viết `(String)`. Trong `Box<Integer>`, `get()` được dùng như `Integer` và có thể tự mở hộp (`unboxing`) khi tính toán.

Nếu sửa thành:

```java
Box<String> labelBox = new Box<>(42); // Không biên dịch
```

trình biên dịch sẽ từ chối do `Integer` không đáp ứng kiểu `String` mà biến `labelBox` yêu cầu. Đây là lợi ích quan trọng: phát hiện sai sót **trước khi chạy**, gần nơi truyền dữ liệu sai, thay vì chờ đến một nhánh ép kiểu xa hơn.

Với collection, nguyên tắc tương tự:

```java
List<String> words = new ArrayList<>();
words.add("Java");
// words.add(42);  // Bỏ // sẽ gây lỗi biên dịch
String first = words.get(0); // Không cần ép kiểu tường minh
```

Đoạn trên là **mã minh họa trong một phương thức**, cần import `java.util.List` và `java.util.ArrayList`. `List<String>` ràng buộc **kiểu phần tử** là `String`; `List<Object>` thì không. Cũng cần nhớ `List<String>` không phải kiểu con của `List<Object>`: generic Java mặc định **bất biến** (`invariant`), nhằm tránh những phép thêm phần tử sai kiểu qua tham chiếu có tham số kiểu khác.

### So sánh thiết kế

| Hợp đồng sử dụng | Mức bảo đảm ở lúc biên dịch | Việc người dùng API thường phải làm |
|---|---|---|
| `Object get()` | Chỉ biết kết quả là tham chiếu `Object` | Tìm hiểu kiểu mong đợi, kiểm tra hoặc ép kiểu trước khi dùng API riêng. |
| `List<Object>` | Từng phần tử có kiểu tĩnh `Object` | Chấp nhận dữ liệu nhiều kiểu; kiểm tra khi cần thao tác đặc thù. |
| `T get()` trong `Box<T>` | Ràng buộc theo tham số kiểu cụ thể | Dùng đúng kiểu được khai báo; lỗi đưa dữ liệu sai kiểu thường bị chặn khi biên dịch. |
| `List<String>` | Hạn chế phần tử thêm qua API được kiểm tra kiểu thành `String` | Lấy phần tử như `String` mà không tự ép kiểu. |

## 5. Khi chưa thể dùng generic: kiểm tra kiểu trước khi sử dụng

Với API cũ hoặc nguồn dữ liệu thực sự không biết trước kiểu, có thể kiểm tra bằng `instanceof` thay vì ép mù. Java 17 hỗ trợ **pattern matching for `instanceof`**:

Lưu thành `SafeReadDemo.java`:

```java
public class SafeReadDemo {
    public static void main(String[] args) {
        Object item = 42;

        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        } else {
            System.out.println("Không phải String");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SafeReadDemo.java
java SafeReadDemo
```

`stdout`:

```text
Không phải String
```

Trong nhánh đúng, biến `text` đã có kiểu `String`; nếu không phù hợp, ta xử lý nhánh còn lại một cách tường minh. Kiểm tra này phù hợp khi dữ liệu **chủ ý có nhiều kiểu** hoặc đi qua một ranh giới thiếu thông tin kiểu. Nếu toàn bộ dữ liệu về bản chất phải cùng một kiểu, hãy mô hình hóa hợp đồng bằng generic hoặc lớp dữ liệu cụ thể từ đầu, thay vì rải `instanceof` khắp chương trình.

## 6. Generics có chặn được mọi `ClassCastException` không?

**Không.** Trong mã Java dùng tham số kiểu một cách nhất quán, generics phát hiện được nhiều sai sót ngay lúc biên dịch. Tuy nhiên, Java triển khai generic chủ yếu qua **type erasure**: phần lớn thông tin tham số kiểu không được duy trì như một kiểm tra kiểu cho từng phần tử trong collection tại runtime. Mã dùng **raw type**, ép kiểu không kiểm tra, phản xạ hoặc tương tác với mã cũ vẫn có thể phá ràng buộc.

Ví dụ cố ý vi phạm hợp đồng generic, lưu thành `RawTypeTrapDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeTrapDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List raw = names;  // Raw type: đánh mất kiểm tra tham số kiểu
        raw.add(123);     // Có thể được biên dịch nhưng báo unchecked warning

        try {
            String first = names.get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("Dữ liệu sai kiểu xuất hiện khi đọc");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked RawTypeTrapDemo.java
java RawTypeTrapDemo
```

`stdout` của lệnh `java`:

```text
Dữ liệu sai kiểu xuất hiện khi đọc
```

Lệnh `javac` còn cảnh báo về raw type và lời gọi `add` không được kiểm tra kiểu; nội dung cảnh báo cụ thể phụ thuộc trình biên dịch. Tại dòng `names.get(0)`, trình biên dịch đã chèn kiểm tra ép về `String` cho giá trị lấy ra. Vì dữ liệu bên trong thực tế là `Integer`, `ClassCastException` vẫn xảy ra mặc dù dòng đọc không có ép kiểu tường minh trong mã nguồn.

**Bài học:** đừng bỏ qua cảnh báo `rawtypes` và `unchecked`; khi phải tích hợp API cũ, hãy thu hẹp phạm vi tương tác, xác thực dữ liệu ở biên và trả về API đã được ràng buộc kiểu.

## 7. Chọn `Object` hay generic trong trường hợp nào?

- Dùng **generic** khi các giá trị của một collection, hộp dữ liệu, tham số hoặc kết quả phương thức có **quan hệ kiểu cần được bảo đảm** cho người gọi: ví dụ `List<Order>`, `Repository<T>`, `Optional<User>` hoặc `Box<T>`.
- Dùng **`Object` có chủ đích** khi hợp đồng thật sự chấp nhận mọi đối tượng và cách xử lý không đòi hỏi giả định một kiểu cụ thể; ví dụ một tham số chỉ dùng `toString()` hoặc một ranh giới API rất tổng quát. Không dùng `Object` chỉ để né thiết kế kiểu.
- Nếu giá trị hợp lệ có **một số biến thể xác định**, cân nhắc một interface chung hoặc mô hình kiểu có phân nhánh rõ ràng, thay cho một tập các phép ép tùy tiện.
- Khi đọc dữ liệu bên ngoài như JSON, thông điệp hoặc cache, **kiểm tra/giải mã** sang kiểu được kỳ vọng tại ranh giới. Khai báo một tham số generic ở mã ứng dụng không tự xác thực payload bên ngoài.
- Nếu cần nhiều kiểu trong cùng collection, hãy diễn đạt điều đó thành API dễ hiểu và dùng kiểm tra/dispatch phù hợp; việc đổi từ `List<Object>` sang `List<String>` chỉ hợp lý khi các phần tử thực sự phải là chuỗi.

### Sai lầm thường gặp

**“Ép kiểu là chuyển đổi dữ liệu.”** Không đúng với ép kiểu tham chiếu: `(String) object` chỉ kiểm tra object đang tham chiếu tới kiểu phù hợp, không tạo một chuỗi mới từ một số.

**“Đã có generic thì JVM sẽ không bao giờ ném `ClassCastException`.”** Không đúng khi có raw type, unchecked cast hoặc dữ liệu bị đưa vào qua đường không an toàn.

**“Dùng `List<Object>` đã đủ an toàn vì cũng là generic.”** Tham số `Object` không biểu đạt ràng buộc chỉ nhận `String`; cả `String` và `Integer` đều hợp lệ.

**“Chỉ cần `try/catch` mọi nơi là xong.”** Bắt ngoại lệ giúp ứng dụng xử lý thất bại, nhưng không giải quyết hợp đồng dữ liệu sai. Nên giảm ép kiểu bằng thiết kế kiểu trước; xử lý ngoại lệ tại ranh giới thật sự cần thiết.

## 8. Tự kiểm tra

1. Vì sao `Object x = 42; String s = (String) x;` có thể biên dịch nhưng ném `ClassCastException`? Hãy chỉ ra kiểu tĩnh và kiểu thực tế của `x`.
2. Trong `List<Object> values`, tại sao `values.add("A")` và `values.add(10)` đều hợp lệ? Nếu mọi phần tử đều phải là chuỗi, kiểu nào diễn đạt đúng ý định hơn?
3. Nếu `List<String> names` bị thêm một `Integer` thông qua raw type, lỗi có thể xuất hiện ở thao tác đọc hay thao tác thêm? Vì sao?

**Đáp án định hướng:** (1) Kiểu tĩnh của `x` là `Object`, kiểu thực tế là `Integer`; JVM bác phép ép thành `String`. (2) Vì `Object` cho phép mọi kiểu tham chiếu; dùng `List<String>` để ràng buộc phần tử là chuỗi. (3) Phép thêm qua raw type có thể chỉ tạo cảnh báo; lúc đọc thành `String`, phép kiểm tra ép kiểu do trình biên dịch chèn mới phát hiện đối tượng `Integer`.

Thông điệp cốt lõi là: **dùng `Object` làm mất khả năng mô tả chính xác kiểu dữ liệu tại điểm gọi; ép kiểu tường minh chuyển một phần trách nhiệm kiểm tra sang JVM lúc chạy. Generics giúp trình biên dịch kiểm tra hợp đồng kiểu sớm hơn, nhưng cần tránh các đường truy cập không an toàn để giữ lợi ích đó.**
