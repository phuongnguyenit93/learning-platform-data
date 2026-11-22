# Nối chuỗi trong một biểu thức so với tích lũy qua vòng lặp trong Java

Trong Java, **cách nối chuỗi nên phụ thuộc vào cách dữ liệu được tạo ra**. Nếu chỉ ghép vài thành phần trong **một biểu thức**, toán tử `+` thường rõ ràng, dễ bảo trì và được trình biên dịch/JVM hiện đại tối ưu. Nếu **tích lũy văn bản sau nhiều lần lặp**, sử dụng `StringBuilder` hoặc một API ghép phù hợp thường tránh được việc liên tục tạo chuỗi trung gian và sao chép tiền tố đã có.

Ví dụ hai cách dưới đây đều có thể cho kết quả `"Java 17"`, nhưng chúng diễn đạt những công việc khác nhau:

```java
String oneExpression = "Java" + " " + 17; // Một biểu thức nối.

StringBuilder builder = new StringBuilder();
builder.append("Java");
builder.append(" ");
builder.append(17);
String accumulated = builder.toString();   // Tích lũy nhiều bước.
```

Không có quy tắc “**mọi phép `+` đều chậm**” hay “**luôn phải dùng `StringBuilder`**”. Cần phân biệt nơi mã nguồn tạo một biểu thức nối với nơi chương trình xây kết quả qua nhiều vòng lặp hoặc nhiều nhánh.

## 1. Cơ sở: `String` bất biến và kết quả của phép nối

Đối tượng `String` là *immutable*: giá trị văn bản bên trong một đối tượng đã tạo không thể bị sửa qua API thông thường. Do đó:

```java
String first = "Java";
String second = first + " 17";

System.out.println(first);  // Java
System.out.println(second); // Java 17
```

Biểu thức nối tạo ra **giá trị chuỗi kết quả**, không thêm ký tự vào đối tượng `first` đang tồn tại. Trong tình huống có giá trị mới khác giá trị cũ, cần có một đối tượng `String` biểu diễn kết quả mới. Cách JVM tạo kết quả có thể được tối ưu tùy JDK, nhưng tính bất biến của đối tượng là hợp đồng không đổi.

Phép gán cộng `+=` cũng không biến `String` thành kiểu mutable:

```java
String message = "A";
String oldMessage = message;

message += "B";  // Tương đương về kết quả với message = message + "B";

System.out.println(message);    // AB
System.out.println(oldMessage); // A
```

Biến `message` nhận tham chiếu tới giá trị mới; `oldMessage` tiếp tục giữ nội dung `"A"`. Nếu một vòng lặp thực hiện `message += item` nhiều lần, mỗi vòng về mặt ngữ nghĩa đang xây **giá trị kết quả kế tiếp** từ giá trị trước.

## 2. Nối vài thành phần trong **một biểu thức**: dùng `+` cho dễ đọc

Cú pháp `+` với ít nhất một toán hạng là `String` thực hiện nối văn bản:

```java
String user = "An";
int points = 12;
String label = "User: " + user + ", points: " + points;
// label = "User: An, points: 12"
```

Một biểu thức có nhiều phần vẫn là một đơn vị mã nguồn rõ ràng: JVM có thể xây kết quả mà không cần lặp qua một chuỗi tiền tố được mở rộng thủ công. Ví dụ thường phù hợp:

- Tạo thông điệp ngắn từ hai đến vài biến: `"Hello, " + name + "!"`.
- Tạo nhãn hiển thị: `"Score: " + score`.
- Ghép một vài thành phần cấu hình nếu cú pháp dễ hiểu và dữ liệu đã được kiểm tra.

Với các toán hạng là **hằng thời gian biên dịch**, trình biên dịch có thể nối thành một hằng chuỗi ngay khi biên dịch:

```java
String s = "Ja" + "va"; // Constant expression, giá trị "Java".
```

Đây là lý do không thể suy luận rằng `"Ja" + "va"` phải cấp phát các chuỗi trung gian tại mỗi lần chạy.

### Java hiện đại tối ưu phép nối như thế nào?

Trước Java 9, nhiều phép nối chuỗi được trình biên dịch triển khai tương đương với tạo và sử dụng `StringBuilder`. Từ **Java 9**, JEP 280 (*Indify String Concatenation*) đưa ra cơ chế tạo bytecode bằng `invokedynamic`, cho phép runtime chọn chiến lược nối phù hợp qua `java.lang.invoke.StringConcatFactory`.

Trong Java 17+, trình biên dịch thông thường có thể dùng cơ chế này cho biểu thức nối động, thay vì cố định một chuỗi lệnh tạo `StringBuilder` trực tiếp. Những tối ưu cụ thể phụ thuộc phiên bản JVM, loại giá trị và bối cảnh JIT. Tuy nhiên, điều quan trọng với người học là:

1. **Một biểu thức nối ngắn bằng `+` thường là lựa chọn tốt.** Mã rõ ràng và JVM có cơ hội tối ưu.
2. **Đừng tự viết `new StringBuilder().append(...).append(...).toString()` cho mọi dòng `+`** khi không có lý do rõ ràng. Mã có thể dài hơn mà không nhanh hơn trong điều kiện thực tế.
3. **Tối ưu cho một biểu thức không tự động giải quyết tích lũy qua nhiều vòng lặp.** Đó là cấu trúc thuật toán khác, cần xét riêng.

## 3. Tích lũy qua vòng lặp bằng `+=`: chi phí nằm ở tiền tố lặp lại

Xét đoạn mã:

```java
String result = "";

for (int i = 1; i <= 4; i++) {
    result += i;
}

System.out.println(result); // 1234
```

Vòng lặp tạo kết quả liên tiếp:

```text
Lần 1: ""     + "1" → "1"
Lần 2: "1"    + "2" → "12"
Lần 3: "12"   + "3" → "123"
Lần 4: "123"  + "4" → "1234"
```

Ở mỗi bước, phép nối cần tạo giá trị mới từ toàn bộ phần đã tích lũy và phần tiếp theo. **Nếu các lần nối lần lượt sao chép toàn bộ tiền tố**, tổng lượng dữ liệu được xử lý trong trường hợp `n` đoạn có độ dài gần bằng nhau tăng theo dãy:

```text
1 + 2 + 3 + ... + n = n(n + 1) / 2
```

Đây là **mô hình chi phí có thể tiến tới bậc O(n²)** theo số đoạn khi dùng nối tạo chuỗi mới qua mỗi vòng. Thời gian thực tế có thể khác do runtime tối ưu, độ dài các đoạn, chi phí số hóa dữ liệu và JIT. Không nên tuyên bố rằng Java 17 sẽ luôn tốn đúng bậc thời gian đó với mọi đoạn mã, nhưng mô hình cho thấy **vì sao cách lặp với `+=` là lựa chọn kém ổn định khi dữ liệu tăng lớn**.

Việc lặp tạo các kết quả trung gian cũng có thể tăng áp lực lên bộ cấp phát và garbage collector. Nếu chuỗi chỉ có ba phần và vòng lặp chạy rất ít lần, chi phí có thể không đáng kể; nếu dựng hàng nghìn mục, vấn đề trở nên quan trọng hơn.

## 4. `StringBuilder`: một vùng đệm mutable cho nhiều bước nối

`StringBuilder` là lớp có thể thay đổi nội dung. Nó hỗ trợ `append()`, `insert()`, `delete()`, `setCharAt()`, v.v. Thay vì liên tiếp tạo `String` trung gian làm kết quả tích lũy, mã có thể cập nhật **cùng một builder**:

```java
StringBuilder builder = new StringBuilder();

for (int i = 1; i <= 4; i++) {
    builder.append(i);
}

String result = builder.toString();
System.out.println(result); // 1234
```

Cơ chế cần hiểu:

- `new StringBuilder()` tạo một đối tượng giữ bộ đệm ký tự bên trong (chi tiết biểu diễn có thể thay đổi giữa các JDK).
- `append(value)` thêm biểu diễn văn bản của giá trị vào cuối nội dung hiện tại, và trả về chính builder để có thể gọi liên tiếp.
- Khi không đủ dung lượng, builder có thể mở rộng bộ đệm; việc mở rộng vẫn có chi phí, nhưng không yêu cầu tạo `String` kết quả sau **mỗi** lần thêm.
- `toString()` tạo giá trị `String` có nội dung tại thời điểm gọi, dùng để trả về, lưu hoặc chia sẻ với phần mềm khác.
- `StringBuilder` **không bảo đảm an toàn luồng** nếu nhiều luồng cùng sửa một instance.

Đối với mẫu thêm tuần tự các đoạn có tổng độ dài `m`, builder thường giúp tránh việc liên tục sao chép tiền tố ở mỗi vòng. Không phải mọi thao tác trên builder đều luôn có độ phức tạp tuyến tính: `insert()` hoặc `delete()` ở vị trí giữa có thể dịch chuyển dữ liệu; tạo quá ít dung lượng ban đầu cũng có thể gây cấp phát lại.

### Có thể nối liên tiếp bằng cách gọi chuỗi phương thức

```java
StringBuilder builder = new StringBuilder();
builder.append("Name: ")
       .append("An")
       .append(", score: ")
       .append(12);

String output = builder.toString();
// "Name: An, score: 12"
```

Cách gọi này thường hữu ích trong mã cần bổ sung nhiều phần có điều kiện hoặc lặp. Với **một biểu thức ngắn** `"Name: " + name + ", score: " + score` vẫn có thể rõ ràng hơn.

## 5. Chương trình Java 17+ hoàn chỉnh: cùng kết quả, cách tích lũy khác nhau

Tạo tệp `ConcatLoopDemo.java`:

```java
public class ConcatLoopDemo {
    private static String withPlusEquals(int count) {
        String result = "";

        for (int i = 1; i <= count; i++) {
            if (i > 1) {
                result += ", ";
            }
            result += i;
        }
        return result;
    }

    private static String withBuilder(int count) {
        StringBuilder result = new StringBuilder();

        for (int i = 1; i <= count; i++) {
            if (i > 1) {
                result.append(", ");
            }
            result.append(i);
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String left = withPlusEquals(4);
        String right = withBuilder(4);

        System.out.println("plusEquals = " + left);
        System.out.println("builder = " + right);
        System.out.println("sameContent = " + left.equals(right));

        String oneExpression = "Items: " + 4 + ", ready: " + true;
        System.out.println(oneExpression);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ConcatLoopDemo.java
java ConcatLoopDemo
```

Kết quả chính xác:

```text
plusEquals = 1, 2, 3, 4
builder = 1, 2, 3, 4
sameContent = true
Items: 4, ready: true
```

Hai hàm trả về **nội dung như nhau**. Điều khác là mô hình tạo kết quả: `withPlusEquals()` liên tục nối vào một biến `String` qua nhiều lượt, còn `withBuilder()` bổ sung vào một đối tượng có thể thay đổi rồi gọi `toString()` ở cuối. Vì vậy, đối với tích lũy qua vòng lặp với dữ liệu tăng, `StringBuilder` thường là lựa chọn dễ dự đoán hơn về chi phí.

Không dùng chương trình này để “đo hiệu năng”: nó chỉ chứng minh **tính đúng đắn và sự tương đương đầu ra**. Sự khác biệt về thời gian chạy cần một phép đo benchmark phù hợp.

## 6. Toán tử `+` có những quy tắc dễ gây sai kết quả

Phép `+` trên `String` vẫn tuân theo thứ tự kết hợp trái và string conversion. Nếu biểu thức chứa phép tính số, cần ngoặc cho rõ ý:

```java
System.out.println("Sum = " + 1 + 2);   // Sum = 12
System.out.println("Sum = " + (1 + 2)); // Sum = 3
```

Khi đối số là `null`, phép nối có thể sinh chữ `"null"`; `concat(null)` lại có thể ném `NullPointerException`. Những quy tắc cú pháp và null này đã có bài riêng. Trong bài này, điều cần phân biệt là **một biểu thức ngắn** với **tích lũy tiền tố qua nhiều lần lặp**.

## 7. Dấu phân cách: đừng nối dư dấu cuối hoặc xây chuỗi bằng cách cắt bớt

Một lỗi thường gặp khi ghép danh sách là thêm dấu `, ` sau mọi phần tử rồi cắt hai ký tự ở cuối. Cách này cần xử lý danh sách rỗng và có thể dẫn đến truy cập sai chỉ số.

Thay vào đó, chỉ thêm dấu phân cách **trước phần tử thứ hai trở đi**:

```java
StringBuilder builder = new StringBuilder();
String[] tags = {"java", "core", "string"};

for (String tag : tags) {
    if (builder.length() > 0) {
        builder.append(", ");
    }
    builder.append(tag);
}

System.out.println(builder); // java, core, string
```

Đoạn này chỉ dùng được nguyên tắc `builder.length() > 0` khi các phần tử đầu tiên không phải chuỗi rỗng; với phần tử `""`, kết quả có thể thiếu dấu phân cách mong muốn. Một cách chắc chắn hơn là dùng **cờ `first`** hoặc **chỉ số vòng lặp**. Cách sau áp dụng đúng kể cả khi phần tử rỗng:

```java
String[] tags = {"", "java", "core"};
StringBuilder builder = new StringBuilder();

for (int i = 0; i < tags.length; i++) {
    if (i > 0) {
        builder.append(", ");
    }
    builder.append(tags[i]);
}

System.out.println("[" + builder + "]"); // [, java, core]
```

Đối với danh sách đã có, `String.join()` hoặc `StringJoiner` thường đơn giản hơn. Chúng có ngữ nghĩa dấu phân cách rõ ràng và tránh việc tự quản lý điều kiện phần tử đầu/cuối:

```java
java.util.List<String> tags =
        java.util.List.of("java", "core", "string");

String joined = String.join(", ", tags);
System.out.println(joined); // java, core, string
```

**Chọn API dựa trên cấu trúc dữ liệu**: `String.join()` khi đã có danh sách/varargs chuỗi; `StringJoiner` khi thêm các phần tử dần dần với delimiter; `StringBuilder` khi cần xây nhiều dạng nội dung tùy biến.

## 8. `StringJoiner`: tích lũy nhiều phần với delimiter, prefix và suffix

Tạo tệp `StringJoinerDemo.java`:

```java
import java.util.List;
import java.util.StringJoiner;

public class StringJoinerDemo {
    public static void main(String[] args) {
        List<String> tags = List.of("java", "core", "string");

        StringJoiner joiner = new StringJoiner(", ", "[", "]");
        for (String tag : tags) {
            joiner.add(tag);
        }

        System.out.println("joiner = " + joiner);
        System.out.println("stringJoin = " + String.join(" | ", tags));

        StringJoiner empty = new StringJoiner(", ", "[", "]");
        System.out.println("emptyJoiner = " + empty);
    }
}
```

Biên dịch và chạy:

```bash
javac StringJoinerDemo.java
java StringJoinerDemo
```

Kết quả:

```text
joiner = [java, core, string]
stringJoin = java | core | string
emptyJoiner = []
```

`StringJoiner` hỗ trợ thêm phần tử dần qua `add()`, tự quản lý dấu phân cách giữa các phần tử và có thể thêm tiền tố/hậu tố. Đây là giải pháp thuận tiện khi yêu cầu chính là **nối danh sách**, thay vì xây một văn bản có cấu trúc phức tạp.

Nếu cần nối các giá trị từ stream, có thể dùng `Collectors.joining(", ")`. Tuy vậy, không cần chuyển một danh sách nhỏ sang stream chỉ để thay một lời gọi `String.join()` rõ ràng.

## 9. Khi nào nên cấp trước dung lượng `StringBuilder`?

Bạn có thể cung cấp dung lượng ban đầu khi đã biết **ước lượng hợp lý** số UTF-16 code units của kết quả:

```java
String[] chunks = {"abc", "def", "ghi"};
int estimatedLength = 0;

for (String chunk : chunks) {
    estimatedLength += chunk.length();
}

StringBuilder builder = new StringBuilder(estimatedLength);
for (String chunk : chunks) {
    builder.append(chunk);
}

System.out.println(builder.toString()); // abcdefghi
```

Ví dụ này là fragment đặt trong một phương thức; `estimatedLength` được tính đúng bằng tổng độ dài ba chuỗi. Đặt capacity ban đầu có thể giảm số lần phải mở rộng bộ đệm.

Cần phân biệt:

- **`capacity()`** của builder: dung lượng bộ đệm có thể chứa trước khi cần mở rộng.
- **`length()`** của builder: độ dài văn bản thực đang có, tính bằng UTF-16 code units.
- `new StringBuilder(100)` **không** tạo sẵn một chuỗi dài 100 ký tự; ban đầu `length() == 0`.
- `ensureCapacity(minimumCapacity)` có thể bảo đảm dung lượng tối thiểu khi cần, nhưng không thêm nội dung.
- Dung lượng ước lượng quá lớn sẽ tiêu thụ bộ nhớ không cần thiết; đừng cấp phát quá mức theo một phỏng đoán thiếu cơ sở.

Với dữ liệu rất lớn, phép tính tổng độ dài bằng `int` cần xét giới hạn và tránh tràn số nguyên. Với công việc thông thường, dùng builder mặc định thường đã đủ; chỉ tối ưu capacity khi việc đo đạc cho thấy có lợi.

## 10. `StringBuilder.toString()` tạo một ảnh chụp giá trị chuỗi

Khi lấy kết quả từ builder, `String` trả về không trở thành “cửa sổ sống” vào trạng thái của builder:

```java
StringBuilder builder = new StringBuilder("A");
String before = builder.toString();

builder.append("B");
String after = builder.toString();

System.out.println("before = " + before);
System.out.println("after = " + after);
```

Kết quả:

```text
before = A
after = AB
```

Biến `before` vẫn là `"A"` vì đối tượng `String` bất biến. Nếu cần tạo nhiều bản ghi snapshot ở các thời điểm khác nhau, gọi `toString()` ở mỗi thời điểm là hành vi đúng, nhưng cũng tạo thêm giá trị kết quả tương ứng.

Thông thường, nếu chỉ cần kết quả cuối cùng, nên **tích lũy hết rồi gọi `toString()` một lần**. Đừng gọi `toString()` mỗi vòng để rồi dùng kết quả đó làm chuỗi nguồn cho vòng lặp tiếp theo; như vậy sẽ làm mất lợi ích chính của bộ đệm tích lũy.

## 11. Unicode không thay đổi nguyên tắc lựa chọn, nhưng ảnh hưởng độ dài

`String.length()` và `StringBuilder.length()` tính theo **UTF-16 code units**. Một Unicode code point ngoài BMP như nhiều emoji có thể chiếm hai code units:

```java
String emoji = "\uD83D\uDE00"; // 😀
String one = "A" + emoji + "B";

StringBuilder builder = new StringBuilder();
builder.append("A").append(emoji).append("B");

System.out.println(one.equals(builder.toString())); // true
System.out.println(one.length());                    // 4
System.out.println(builder.length());                // 4
```

Tính đúng của phép nối không bị thay đổi: cả `+` và `append()` đều giữ nguyên dãy đơn vị mã của các đoạn nguồn trong ví dụ. Tuy nhiên, khi ước lượng capacity, giới hạn độ dài hoặc cắt văn bản, không được mặc định “số ký tự nhìn thấy” luôn bằng `length()`.

Một builder cũng có thể bị sửa theo chỉ số với `setCharAt()`, `delete()` hoặc `insert()`; việc cắt giữa surrogate pair có thể tạo văn bản Unicode không hợp lệ. Nếu chỉ cần nối nguyên vẹn các đoạn Unicode đã hợp lệ, các phép `append()` tuần tự thường đơn giản hơn nhiều.

## 12. Giới hạn, chia sẻ nhiều luồng và API liên quan

### Không chia sẻ một `StringBuilder` để sửa đồng thời mà thiếu đồng bộ

`StringBuilder` không đồng bộ hóa các phương thức của nó. Nếu hai luồng cùng gọi `append()` trên một instance, nội dung có thể bị race condition và không có bảo đảm đúng thứ tự hoặc toàn vẹn.

Nếu mỗi request hoặc mỗi tác vụ tạo builder **cục bộ riêng**, không có vấn đề chia sẻ đó. Với trường hợp thực sự cần thao tác trên bộ đệm chung giữa các luồng, cân nhắc đồng bộ thích hợp hoặc `StringBuffer` (các phương thức chính được đồng bộ hóa). Dù dùng `StringBuffer`, một quy trình gồm nhiều lời gọi vẫn cần kiểm tra tính nguyên tử ở cấp quy trình.

### `StringBuilder` không cần cho mọi đoạn mã có vòng lặp

Trường hợp này không phải tích lũy một chuỗi qua các lượt:

```java
for (int i = 0; i < 3; i++) {
    System.out.println("Item " + i);
}
```

Mỗi vòng chỉ cần một **thông điệp độc lập**, không dựng một kết quả lớn từ các thông điệp cũ. Dùng `"Item " + i` là rõ ràng và hoàn toàn hợp lý. Vấn đề đáng cân nhắc là khi **cùng một biến chuỗi kết quả** được nối rồi gán lại liên tục, ví dụ `result += item`.

### Tránh ghép chuỗi vô ích khi API đã có tham số cấu trúc

Ví dụ câu SQL có tham số, logging theo mẫu placeholder hoặc API xuất CSV/JSON có quy tắc escape riêng thường nên dùng khả năng cấu trúc của API đó. Không dùng nối chuỗi thủ công để thay thế cơ chế escape, tham số hóa hoặc serialize đúng chuẩn.

Lựa chọn `StringBuilder` chỉ giải quyết cách dựng chuỗi và chi phí bộ đệm; nó **không tự giải quyết** nguy cơ SQL injection, lỗi escaping JSON hay cách định dạng ngày/số theo locale.

## 13. So sánh hiệu năng đúng cách

Đừng kết luận “nhanh hơn X lần” chỉ từ một lần chạy `System.nanoTime()`. Kết quả vi mô bị ảnh hưởng bởi JIT warmup, dead-code elimination, cấp phát/GC, dữ liệu đầu vào, CPU và phiên bản JVM.

Nếu thực sự cần so sánh:

1. Định nghĩa công việc giống nhau: cùng dữ liệu đầu vào, số vòng, cùng kết quả đầu ra.
2. Tạo các phương án có cùng ngữ nghĩa; tránh trường hợp nhánh này xử lý thêm dữ liệu hoặc khác delimiter.
3. Dùng công cụ benchmark phù hợp như **JMH**, có warmup, measurement, fork và cơ chế tiêu thụ kết quả để tránh JVM loại bỏ phép tính.
4. Thử dữ liệu có kích thước thực tế (vài phần tử, hàng trăm, hàng nghìn…) và, khi liên quan, nhiều kiểu Unicode/độ dài đoạn.
5. Đo cả thời gian lẫn lượng cấp phát hoặc GC nếu đó là vấn đề hiệu năng cần tối ưu.
6. Kiểm tra kết quả trước và sau mọi thay đổi tối ưu.

Quy tắc thiết kế vẫn hữu ích ngay cả khi chưa benchmark: **`+` cho một biểu thức ngắn; `StringBuilder` cho một tiến trình tích lũy nhiều đoạn trong vòng lặp**. Khi khác biệt không quan trọng, mã đơn giản và dễ hiểu là ưu tiên.

## 14. Lỗi phổ biến

| Lỗi | Vì sao có vấn đề? | Hướng sửa |
| --- | --- | --- |
| “Mỗi `+` đều chậm, phải thay bằng `StringBuilder`.” | Java hiện đại tối ưu biểu thức nối, tự viết builder có thể chỉ tăng độ phức tạp mã. | Dùng `+` cho biểu thức nhỏ; đo khi thật sự cần. |
| “`result += part` sửa `String` hiện tại.” | `String` bất biến; biến nhận giá trị mới sau mỗi lượt nối. | Dùng builder khi cần tích lũy nhiều lần. |
| “JDK 17 tự động biến mọi vòng lặp `+=` thành một builder duy nhất.” | Không có bảo đảm tổng quát như vậy trong hợp đồng ngôn ngữ. | Chọn cấu trúc tích lũy tường minh khi cần hiệu quả ổn định. |
| “`"Sum: " + 1 + 2` in `Sum: 3`.” | Sau khi bắt đầu nối chuỗi, các toán hạng tiếp theo được nối theo thứ tự. | Viết `"Sum: " + (1 + 2)`. |
| “`new StringBuilder(100)` có sẵn 100 ký tự.” | Tham số constructor là **capacity**, không phải length. | Dùng `append()` để thêm nội dung. |
| “`StringBuilder` luôn an toàn đa luồng.” | `StringBuilder` mutable và không đồng bộ hóa. | Giữ builder cục bộ hoặc đồng bộ thích hợp. |
| “`String.join()` chỉ hữu ích khi vòng lặp lớn.” | Đây là API diễn đạt ý định ghép danh sách và quản lý delimiter. | Dùng khi đã có các thành phần. |
| “`builder.toString()` là một view mutable.” | Kết quả là `String` bất biến, không cập nhật khi builder đổi. | Chỉ gọi lại `toString()` nếu muốn snapshot mới. |
| “Biến `null` được bỏ qua khi nối.” | Phép nối chuỗi có thể tạo chữ `"null"`. | Kiểm tra và đặt chính sách null rõ ràng. |
| “Builder xử lý đúng escape JSON/CSV/SQL.” | Nó chỉ nối giá trị, không hiểu cú pháp hay an toàn của định dạng đích. | Dùng parser/serializer hoặc API tham số phù hợp. |

## 15. Tự kiểm tra

**Câu 1.** Đoạn mã dưới đây tích lũy qua vòng lặp hay chỉ nối một biểu thức trong từng vòng?

```java
for (int i = 0; i < 3; i++) {
    String line = "Index: " + i;
    System.out.println(line);
}
```

Đây là **mỗi vòng một biểu thức độc lập**, không có biến kết quả tích lũy dài thêm qua các lượt. Không bắt buộc chuyển sang `StringBuilder`.

**Câu 2.** Đoạn mã sau có lỗi gì khi số vòng lớn?

```java
String output = "";
for (String item : items) {
    output = output + item;
}
```

Mỗi vòng xây giá trị kết quả mới từ tiền tố cũ và `item`. Với nhiều đoạn, việc phải xử lý lại tiền tố làm phát sinh chi phí; dùng `StringBuilder.append(item)` trong vòng lặp rồi `toString()` ở cuối thường thích hợp hơn. Đây là fragment giả định biến `items` đã tồn tại.

**Câu 3.** Vì sao `"n=" + 1 + 2` không giống `"n=" + (1 + 2)`?

Biểu thức thứ nhất là `"n=12"`, còn biểu thức thứ hai là `"n=3"`. Cần dùng dấu ngoặc khi thực sự muốn cộng số trước khi nối chuỗi.

**Câu 4.** Nếu danh sách là `["", "A"]` và cần nối bằng dấu phẩy, kết quả mong muốn là `",A"`. Kiểm tra `builder.length() > 0` để quyết định thêm dấu phẩy đã đủ chưa?

Chưa. Sau khi thêm phần tử rỗng đầu tiên, builder vẫn có `length() == 0`, nên cách đó bỏ dấu phẩy. Dùng **chỉ số/cờ phần tử đầu tiên** hoặc `StringJoiner` để không phụ thuộc vào độ dài nội dung.

**Câu 5.** Một builder đã tạo chuỗi `"A"` qua `toString()`; sau đó `append("B")` vào builder. Chuỗi `"A"` có thành `"AB"` không?

Không. Kết quả của `toString()` là một đối tượng `String` bất biến. Muốn lấy nội dung mới, gọi `toString()` lần nữa sau khi đã `append()`.

## Kết luận

- Với **một biểu thức nối ngắn** (ví dụ `"Hello, " + name + "!"`), `+` dễ đọc và thường được Java hiện đại tối ưu tốt.
- Với **một chuỗi kết quả được tích lũy qua nhiều vòng lặp**, `StringBuilder` thường giúp tránh tạo lặp đi lặp lại các giá trị `String` trung gian và sao chép tiền tố.
- Nếu mục đích là nối **các phần tử với dấu phân cách**, xem xét `String.join()` hoặc `StringJoiner`.
- `String` bất biến, `StringBuilder` mutable; `toString()` cung cấp chuỗi kết quả bất biến.
- Xử lý rõ `null`, thứ tự cộng số/nối chuỗi, Unicode, trường hợp danh sách rỗng, và đo bằng benchmark có phương pháp trước khi kết luận hiệu năng.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): tính bất biến, nối chuỗi, `join()`.
- [Java SE 21 API — `java.lang.StringBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html): `append()`, `capacity()`, `ensureCapacity()`, `toString()`.
- [Java SE 21 API — `java.util.StringJoiner`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/StringJoiner.html): quy tắc delimiter, prefix và suffix.
- [OpenJDK JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): cách Java 9+ tối ưu mô hình nối `String` động bằng `invokedynamic`.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ benchmark Java phù hợp với so sánh hiệu năng vi mô.
