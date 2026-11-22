# Xử lý null và đối số không phù hợp

## 1. “Không có giá trị”, “thiếu đối số” và “sai kiểu” là ba tình huống khác nhau

Khi một lời gọi `printf` hoặc `String.format` gặp vấn đề, cần tách ba câu hỏi:

1. Có một đối số ở vị trí được yêu cầu không?
2. Đối số đó có giá trị null không?
3. Nếu khác null, kiểu và giá trị có phù hợp với conversion không?

Ví dụ:

```java
// Có đối số thứ nhất, giá trị của nó là null.
String.format(Locale.ROOT, "%s", (Object) null);

// Không có đối số thứ hai mà mẫu yêu cầu.
String.format(Locale.ROOT, "%2$s", "A");

// Có đối số thứ nhất nhưng nó không hợp với %d.
String.format(Locale.ROOT, "%d", "12");
```

Ba trường hợp không có cùng kết quả. Trường hợp đầu tạo chuỗi `"null"`; trường hợp thứ hai báo thiếu đối số; trường hợp thứ ba báo sai kiểu chuyển đổi.

Formatter là công cụ **biểu diễn dữ liệu**, không phải bộ kiểm tra đầy đủ tính hợp lệ của dữ liệu nghiệp vụ. Một giá trị được formatter chấp nhận chưa chắc phù hợp yêu cầu ứng dụng.

## 2. Null làm đối số không mặc định gây NullPointerException

Với nhiều conversion, formatter có cách biểu diễn null. Quy tắc tổng quát cho các nhóm thông thường là tạo chữ `null`, trừ trường hợp có quy định riêng, nổi bật là boolean.

Với mẫu đơn giản, chưa có giới hạn precision:

| Conversion | Đối số null tạo ra |
| --- | --- |
| `%s` | `null` |
| `%b` | `false` |
| `%c` | `null` |
| `%d` | `null` |
| `%f` | `null` |
| `%tF` | `null` |
| `%S` | `NULL` |

Xem quy tắc null trong [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

Đặc biệt:

```java
Integer quantity = null;
String text = String.format(Locale.ROOT, "quantity=%d", quantity);
```

`text` là `"quantity=null"`. Truyền một `Integer` null theo đường đối số đối tượng không tự bắt buộc mở hộp thành `int`.

Không nên dùng kết quả này để suy ra quantity hợp lệ. Nếu nghiệp vụ yêu cầu số lượng bắt buộc có, hãy kiểm tra trước khi định dạng.

### Precision có thể tác động lên phần biểu diễn null

Với precision phù hợp, chữ biểu diễn null cũng có thể bị giới hạn. Chương trình thực nghiệm ở dưới cho thấy:

```java
String text = String.format(Locale.ROOT, "%.2f", (Object) null);
```

Kết quả quan sát trên JDK 17 và 21 là `"nu"`, không phải số có hai chữ số thập phân.

Điểm học tập là: **precision không biến dữ liệu thiếu thành số hợp lệ**. Đừng trông chờ mẫu số để cung cấp chính sách hiển thị giá trị vắng mặt. Hãy tạo nhánh hiển thị rõ ràng nếu null có ý nghĩa trong dữ liệu.

## 3. Phân biệt null ở chuỗi mẫu

Chuỗi mẫu null là một vấn đề khác:

```java
// Ví dụ lỗi: chính chuỗi định dạng là null.
String.format(Locale.ROOT, (String) null, "A");
```

Lời gọi này ném `NullPointerException`. Nó không có nghĩa “hãy định dạng chữ null”.

Nếu cần in một giá trị null, chuỗi mẫu vẫn phải hợp lệ:

```java
String text = String.format(Locale.ROOT, "%s", (Object) null);
```

Nếu cần in nguyên chữ `null`, đó còn có thể chỉ là một chuỗi thông thường:

```java
String text = "null";
```

Cần xác định null đang nằm ở **tham số nào**, thay vì kết luận chung rằng formatter luôn nhận hoặc luôn từ chối null. Xem [hợp đồng String.format](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#format(java.util.Locale,java.lang.String,java.lang.Object...)).

## 4. Unboxing có thể làm lỗi xảy ra trước formatter

So sánh:

```java
Integer quantity = null;

// Không buộc unboxing: quantity đi vào danh sách đối số đối tượng.
String first = String.format(Locale.ROOT, "%d", quantity);

// Buộc unboxing trong biểu thức Java trước khi gọi formatter.
String second = String.format(Locale.ROOT, "%d", quantity + 1);
```

Dòng đầu có thể tạo `"null"`. Dòng sau ném `NullPointerException` khi Java cần lấy giá trị `int` từ quantity để thực hiện phép cộng.

Formatter chưa nhận được đối số của dòng sau. Thay `%d` thành `%s` cũng không sửa được lỗi unboxing ở biểu thức `quantity + 1`.

Tương tự, lời gọi phương thức trên null xảy ra trước việc định dạng:

```java
String name = null;

// Ví dụ lỗi: name.trim() gây lỗi trước khi String.format xử lý mẫu.
String text = String.format(Locale.ROOT, "%s", name.trim());
```

Khi chẩn đoán, đọc vị trí stack trace và các biểu thức truyền vào. Không quy mọi lỗi quanh một dòng `printf` thành lỗi cú pháp formatter.

## 5. Đối số khác null nhưng sai kiểu

Các giá trị trông tương tự trong văn bản vẫn có thể khác kiểu:

```java
// Ví dụ lỗi: String không tự được phân tích thành số nguyên.
String.format(Locale.ROOT, "%d", "12");

// Ví dụ lỗi: Integer không tự được đổi thành Double để dùng với %f.
String.format(Locale.ROOT, "%f", 12);
```

Cả hai có thể ném `IllegalFormatConversionException`. Ngoại lệ này có thông tin conversion và lớp đối số không tương thích; xem [IllegalFormatConversionException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatConversionException.html).

Đường đi qua `Object...` không tạo ra mọi phép chuyển kiểu số mà người viết mong đợi:

```text
12   → đóng gói thành Integer
12.0 → đóng gói thành Double
```

Nếu yêu cầu là biểu diễn số thực, truyền một giá trị thuộc kiểu được conversion số thực hỗ trợ:

```java
String text = String.format(Locale.ROOT, "%.2f", 12.0);
```

Nếu dữ liệu nguồn là chuỗi, việc phân tích và kiểm tra chuỗi phải xảy ra có chủ ý trước khi định dạng. Không thay bằng `%s` chỉ để giấu việc một trường dự kiến là số đã đi vào hệ thống dưới dạng sai.

### Đúng kiểu vẫn có thể sai giá trị hoặc thiếu trường

`%c` có thể nhận một số nguyên làm mã Unicode, nhưng mã ngoài miền hợp lệ vẫn báo lỗi.

Với conversion ngày/giờ, một đối tượng thời gian phải có thông tin mà conversion yêu cầu. Một đối tượng chỉ biểu diễn ngày không tự có trường giờ hoặc múi giờ để mọi hậu tố ngày/giờ đều dùng được.

Vì vậy kiểm tra không kết thúc ở câu hỏi “có phải Object không?” hoặc “có phải kiểu ngày không?”.

## 6. Thiếu đối số không giống một đối số null

```java
// Ví dụ lỗi: chỉ có một đối số.
String.format(Locale.ROOT, "%2$s", "A");
```

Mẫu yêu cầu đối số thứ hai nhưng danh sách chỉ có một phần tử. `MissingFormatArgumentException` biểu diễn trường hợp thiếu hoặc chỉ số trỏ tới đối số không tồn tại. Xem [MissingFormatArgumentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/MissingFormatArgumentException.html).

So sánh với:

```java
String text = String.format(Locale.ROOT, "%2$s", "A", null);
```

Ở đây đối số thứ hai **có tồn tại** và giá trị của nó là null; kết quả là `"null"`.

Đối số dư lại không mặc định gây lỗi:

```java
String text = String.format(Locale.ROOT, "%s", "A", "B");
```

Kết quả là `"A"`; B không được dùng. Vì thế “không có ngoại lệ” không bảo đảm mẫu đã dùng đủ mọi thông tin dự kiến.

Khi sửa một mẫu dài, nên lập bảng vị trí đối số và conversion, đặc biệt nếu dùng chỉ số `n$` hoặc tái sử dụng bằng `<`.

## 7. Varargs và null: viết rõ ý định

API định dạng nhận danh sách `Object...`. Cần phân biệt:

```java
// Một đối số null.
String.format(Locale.ROOT, "%s", (Object) null);

// Một mảng đối số có một phần tử null.
String.format(Locale.ROOT, "%s", new Object[]{null});

// Bản thân mảng đối số là null.
String.format(Locale.ROOT, "%1$s|%2$s", (Object[]) null);
```

Hai trường hợp đầu cùng có một đối số dữ liệu null.

Trường hợp cuối không phải một mảng rỗng. Theo đường xử lý null của API này, ví dụ tạo `"null|null"`. Không nên dùng khả năng đó như cách tự cung cấp các đối số thiếu; nó dễ che lỗi trong tầng gọi hoặc trong một hàm bao varargs.

Nếu thực sự không có đối số, hãy truyền danh sách rỗng hoặc gọi mà không thêm đối số. Khi mẫu vẫn yêu cầu `%s`, đó là thiếu đối số, không tương đương với việc truyền một đối số null.

Trong mã muốn biểu diễn đúng một giá trị vắng mặt, `(Object) null` làm ý định rõ hơn một literal `null` đứng riêng ở vị trí varargs.

## 8. Ví dụ đầy đủ: phân biệt từng đường xử lý

Tệp `NullFormatArgumentDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.Formatter;
import java.util.IllegalFormatException;
import java.util.Locale;

public class NullFormatArgumentDemo {
    private static void show(String label, String pattern, Object... args) {
        try {
            String text = String.format(Locale.ROOT, pattern, args);
            System.out.println(label + "=[" + text + "]");
        } catch (IllegalFormatException expected) {
            System.out.println(label + "="
                    + expected.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Integer missing = null;

        show("nullString", "%s", (Object) null);
        show("nullBoolean", "%b", (Object) null);
        show("nullCharacter", "%c", (Object) null);
        show("nullInteger", "%d", missing);
        show("nullFloating", "%.2f", (Object) null);
        show("nullDate", "%tF", (Object) null);
        show("nullUpper", "%S", (Object) null);
        show("stringAsInteger", "%d", "12");
        show("integerAsFloating", "%f", 12);
        show("missingArgument", "%2$s", "only-one");
        show("extraArgument", "%s", "A", "B");
        show("explicitNullArray", "%1$s|%2$s", (Object[]) null);

        try {
            int primitive = missing;
            System.out.println(primitive);
        } catch (NullPointerException expected) {
            System.out.println("unboxing=NullPointerException");
        }

        try {
            String.format(Locale.ROOT, (String) null, "A");
        } catch (NullPointerException expected) {
            System.out.println("nullPattern=NullPointerException");
        }

        StringBuilder partial = new StringBuilder();
        try (Formatter formatter = new Formatter(partial, Locale.ROOT)) {
            try {
                formatter.format("prefix:%s; qty:%d", "ok", "bad");
            } catch (IllegalFormatException expected) {
                System.out.println("partialOutput=[" + partial + "]");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac NullFormatArgumentDemo.java
java NullFormatArgumentDemo
```

Kết quả:

```text
nullString=[null]
nullBoolean=[false]
nullCharacter=[null]
nullInteger=[null]
nullFloating=[nu]
nullDate=[null]
nullUpper=[NULL]
stringAsInteger=IllegalFormatConversionException
integerAsFloating=IllegalFormatConversionException
missingArgument=MissingFormatArgumentException
extraArgument=[A]
explicitNullArray=[null|null]
unboxing=NullPointerException
nullPattern=NullPointerException
partialOutput=[prefix:ok; qty:]
```

Các dấu ngoặc vuông do phương thức `show` thêm để nhìn rõ chuỗi đã tạo; chúng không phải một phần formatter tự thêm vào giá trị.

Ví dụ bắt ngoại lệ để minh họa nhiều trường hợp trong một lần chạy. Đây không phải khuyến nghị bắt mọi lỗi rồi chỉ in tên lớp trong ứng dụng thật.

## 9. Định dạng có thể đã ghi một phần trước khi thất bại

Ở cuối chương trình:

```java
formatter.format("prefix:%s; qty:%d", "ok", "bad");
```

Formatter đã ghi `prefix:ok; qty:` vào `StringBuilder` trước khi phát hiện `"bad"` không hợp với `%d`.

Vì vậy một lần định dạng trực tiếp ra đích không phải một giao dịch tự hoàn tác toàn bộ nội dung khi có lỗi.

Nếu cần tránh đưa một dòng chưa định dạng xong ra luồng xuất, có thể tạo chuỗi hoàn chỉnh trước:

```java
// Mã minh họa.
String line = String.format(Locale.ROOT, "name=%s, qty=%d", name, quantity);
System.out.println(line);
```

Nếu `String.format` thất bại, lời gọi `println(line)` chưa xảy ra. Cách này tránh phát ra phần định dạng dở của dòng đó; nó không biến thao tác ghi bên ngoài thành một giao dịch có khả năng hoàn tác hoặc bảo đảm không lỗi I/O.

Với mẫu do ứng dụng sở hữu, cách tốt nhất vẫn là kiểm tra mẫu và dữ liệu ở đúng ranh giới, thay vì dựa vào việc sửa đầu ra sau lỗi.

## 10. Đặt chính sách null ở tầng dữ liệu hiển thị

Có ba lựa chọn thường gặp, tùy ý nghĩa trường dữ liệu.

### Trường bắt buộc

Nếu thiếu số lượng là một lỗi dữ liệu, kiểm tra và báo lỗi rõ trước khi tạo văn bản:

```java
// Mã minh họa.
Objects.requireNonNull(quantity, "quantity is required");
String text = String.format(Locale.ROOT, "quantity=%d", quantity);
```

Đừng để chữ `"null"` lọt vào báo cáo rồi coi nó là một giá trị số hợp lệ.

### Trường tùy chọn

Nếu thiếu dữ liệu là bình thường, tạo nhãn hiển thị riêng:

```java
// Mã minh họa.
String quantityText = quantity == null
        ? "(not provided)"
        : String.format(Locale.ROOT, "%d", quantity);
String text = String.format(Locale.ROOT, "quantity=%s", quantityText);
```

Nhánh cuối dùng `%s` vì `quantityText` lúc đó đã là một văn bản hiển thị.

### Giá trị mặc định theo nghiệp vụ

Chỉ thay null bằng 0, false hoặc chuỗi rỗng khi miền dữ liệu quy định chúng tương đương. Trong nhiều bài toán, “chưa biết số lượng” khác “số lượng bằng 0”; “chưa có câu trả lời” khác “false”.

Không chọn giá trị mặc định chỉ để mẫu khỏi ném ngoại lệ hoặc để output trông gọn.

## 11. Bắt ngoại lệ đúng phạm vi và giữ nguyên nhân

Các lỗi cú pháp hoặc đối số của formatter nằm trong họ `IllegalFormatException`, một loại ngoại lệ không kiểm tra. Xem [IllegalFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatException.html).

Khi xử lý một đầu vào định dạng được phép thay đổi, có thể bắt họ lỗi này tại ranh giới phù hợp và ghi nhận:

- Mẫu hoặc định danh mẫu gây lỗi.
- Loại lỗi cụ thể.
- Vị trí hoặc loại trường dự kiến.
- Nguyên nhân gốc để điều tra.

Không bắt `RuntimeException` cho toàn bộ đường xử lý rồi trả chuỗi rỗng, vì có thể che lỗi trong bước chuẩn bị dữ liệu, `toString()` tùy chỉnh hoặc mã nghiệp vụ.

Cũng không bỏ qua khác biệt giữa `NullPointerException` do unboxing, `IllegalFormatConversionException` do sai kiểu và `MissingFormatArgumentException` do thiếu vị trí. Chúng gợi ý các điểm cần sửa khác nhau.

Với mẫu cố định, kiểm tra nên bao gồm giá trị bình thường, giá trị null nếu được phép, kiểu dữ liệu thật và các trường bắt buộc. Chỉ kiểm tra trường hợp tất cả dữ liệu đều có có thể bỏ sót chính sách null chưa được thiết kế.

## 12. Tự kiểm tra

1. Vì sao `Integer quantity = null` có thể đưa vào `%d` mà không NPE, nhưng `quantity + 1` lại NPE? Biểu thức thứ hai cần unboxing trước khi formatter chạy.
2. `"%2$s"` với `"A", null` có thiếu đối số không? Không; đối số thứ hai tồn tại và có giá trị null.
3. Có nên thay `%d` bằng `%s` để che việc số lượng đang là chuỗi `"12"` không? Chỉ khi miền dữ liệu thật sự muốn biểu diễn văn bản; nếu dự kiến là số, cần sửa bước phân tích/kiểm tra dữ liệu.
4. Nếu formatter báo lỗi ở nửa sau của dòng ghi trực tiếp, phần đầu có chắc chưa xuất hiện không? Không.
5. Null và 0 có tương đương trong báo cáo không? Điều đó thuộc quy tắc dữ liệu của ứng dụng, không thuộc formatter.

Quy trình cần giữ rõ là **kiểm tra dữ liệu → quyết định biểu diễn giá trị vắng mặt → chọn conversion phù hợp → định dạng và xử lý lỗi tại đúng ranh giới**.
