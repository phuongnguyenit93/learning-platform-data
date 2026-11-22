# Thông điệp lồng nhau và các lớp escape cần phân biệt

Một mẫu thông điệp được địa phương hóa có thể chứa **mẫu con** được chọn theo số lượng, giới tính, điều kiện hoặc nhánh nghiệp vụ. Đồng thời, mẫu ấy thường đi qua nhiều tầng biểu diễn: **chuỗi trong Java**, **tệp `.properties` hoặc JSON**, **bộ phân tích `MessageFormat`**, **`ChoiceFormat`/mẫu con**, rồi cuối cùng là **HTML hoặc giao diện người dùng**. Mỗi tầng có cú pháp escape khác nhau.

Nếu nhầm các tầng, chương trình có thể in nguyên `{0}` thay vì chèn đối số, mất dấu nháy đơn trong văn bản, lỗi biên dịch Java, chọn sai câu số ít/số nhiều, hoặc tạo HTML không an toàn. Cách giải quyết là xác định **ký tự thuộc tầng nào**, **tầng nào xử lý trước** và **mẫu con có được parse lại hay chỉ được xem như dữ liệu**.

Bài này dùng `java.text.MessageFormat` và `ChoiceFormat` trong Java 17+ để giải thích cơ chế lồng mẫu, giới hạn của xử lý số nhiều theo ngưỡng và những trường hợp escape thực tế. Các cú pháp plural của thư viện ICU là một hệ thống khác, cần đọc theo tài liệu của chính thư viện đó.

## 1. Thông điệp lồng nhau nghĩa là gì?

Một thông điệp đơn giản có một mẫu:

~~~text
Xin chào {0}, bạn có {1} thông báo.
~~~

Trong đó `{0}` và `{1}` tham chiếu đến các vị trí tương ứng trong mảng đối số. Với câu có số lượng, nội dung tự nhiên có thể thay đổi:

~~~text
0 → You have no messages.
1 → You have one message.
5 → You have 5 messages.
~~~

Thay vì thêm ba câu `if/else` rời rạc, `MessageFormat` có thể dùng một phần định dạng `choice` để chọn nhánh. Nhánh được chọn lại có thể chứa placeholder cần thay tiếp, chẳng hạn `{0,number,integer}`.

Ví dụ mẫu:

~~~text
You have {0,choice,0#no messages|1#one message|1<{0,number,integer} messages}.
~~~

Đây là **mẫu lồng nhau** theo nghĩa phần `choice` chọn một chuỗi mà trong một số nhánh có cú pháp của `MessageFormat` cần xử lý tiếp. Nó không phải là một cây JSON hay một file bundle lồng vào nhau; sự lồng nhau nằm trong **quy trình phân tích/định dạng pattern**.

Có hai ý cần luôn tách riêng:

- **Chọn nhánh:** `ChoiceFormat` dựa vào giá trị số của một đối số để chọn đoạn thông điệp.
- **Thay đối số trong nhánh:** `MessageFormat` có thể format tiếp đoạn nhánh được chọn khi nó có cú pháp placeholder.

Không nên giả định mọi giá trị chuỗi trả về từ mọi formatter đều tự động được parse lần thứ hai. Cơ chế đặc biệt này thuộc cách `MessageFormat` tích hợp `ChoiceFormat`.

## 2. Tầng xử lý: từ mã nguồn tới chuỗi đầu ra

Với một thông điệp được lưu trong mã Java, luồng xử lý phổ biến là:

~~~text
Java source chứa string literal
    ↓ Java compiler hiểu escape của chuỗi Java
Chuỗi pattern tại runtime
    ↓ MessageFormat parse {index}, dấu nháy đơn và định dạng
Phần choice chọn nhánh (nếu có)
    ↓ MessageFormat parse lại nhánh được chọn khi có cú pháp mẫu
Giá trị cuối cùng được chèn thành chuỗi
    ↓ Encode cho HTML/JSON/giao diện nếu cần
Dữ liệu được hiển thị
~~~

Với tệp `.properties`, thay tầng đầu bằng **bộ đọc properties**: nó nhận các escape dành cho định dạng tệp tài nguyên và tạo chuỗi pattern. Với JSON, tầng đầu tương ứng là **JSON parser**.

| Tầng | Cú pháp đặc trưng | Ví dụ quan trọng |
| --- | --- | --- |
| Java string literal | `\\`, `\"`, `\n` | Java source `"A\nB"` tạo runtime string có xuống dòng |
| Java `.properties` | `\n`, `\t`, `\\`, `\uXXXX`, tiếp dòng bằng backslash | Source `line=Hello\n{0}` trở thành pattern có xuống dòng |
| JSON string | `\"`, `\\`, `\n`, `\uXXXX` | JSON được parse **trước** khi thành pattern |
| `MessageFormat` | `{0}`, `{1,number}`, `'`, `''` | `'{0}'` là placeholder nguyên văn; `''{0}''` hiển thị dấu nháy quanh giá trị |
| `ChoiceFormat` | `|`, `#`, `<`, giới hạn số | `0#none|1#one|1<many` |
| HTML | `&amp;`, `&lt;`, escaping cho text/attribute | Đầu ra của MessageFormat vẫn cần encode theo ngữ cảnh |

**Không dùng một hàm “escape tất cả” cho mọi tầng.** Ví dụ `\\` là escape trong chuỗi Java hoặc properties, nhưng dấu backslash **không** phải cách quote dấu ngoặc nhọn trong `MessageFormat`.

## 3. Cú pháp của `ChoiceFormat` bên trong `MessageFormat`

Trong `java.text.MessageFormat`, một format element có dạng tổng quát:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Đối với `choice`:

~~~text
{0,choice,0#none|1#one|1<many}
~~~

Ý nghĩa:

- `0` đầu tiên, trước `,choice,`: **index của đối số** trong mảng đầu vào.
- `0#none`: chọn văn bản `none` khi giá trị đạt nhánh có giới hạn 0.
- `1#one`: chọn `one` ở giới hạn 1.
- `1<many`: chọn `many` khi giá trị **lớn hơn 1**.
- `|`: phân tách các nhánh choice.

`#` biểu diễn giới hạn **bao gồm**; `<` biểu diễn giới hạn **không bao gồm**. `ChoiceFormat` chọn nhánh dựa trên ngưỡng, không tự biết các quy tắc số nhiều của từng ngôn ngữ.

Với mẫu `0#none|1#one|1<many` và các số nguyên không âm:

| Giá trị | Nhánh |
| ---: | --- |
| 0 | `none` |
| 1 | `one` |
| 2 | `many` |
| 5 | `many` |

**Giới hạn nghiệp vụ:** mẫu này chỉ được thiết kế cho số lượng nguyên không âm. Đầu vào âm, phân số hoặc giá trị đặc biệt cần quy tắc được xác định riêng. Đừng áp dụng ngưỡng ví dụ vào mọi bài toán số lượng rồi coi là đúng về ngữ pháp.

## 4. Ví dụ Java 17+: chọn nhánh rồi format mẫu con

Tạo tệp **`NestedChoiceDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class NestedChoiceDemo {
    private static final String PATTERN =
            "You have {0,choice," +
            "0#no messages|" +
            "1#one message|" +
            "1<{0,number,integer} messages}.";

    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(PATTERN, Locale.US);

        System.out.println(formatter.format(new Object[]{0}));
        System.out.println(formatter.format(new Object[]{1}));
        System.out.println(formatter.format(new Object[]{5}));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NestedChoiceDemo.java
java NestedChoiceDemo
~~~

Kết quả:

~~~text
You have no messages.
You have one message.
You have 5 messages.
~~~

Tại nhánh thứ ba, đoạn `{0,number,integer} messages` có placeholder. `MessageFormat` xử lý kết quả của `ChoiceFormat` như **một mẫu cần format tiếp**, nên đối số số lượng được thay ngay trong nhánh.

Điều quan trọng là **đối số không đổi index qua lần parse lồng**: `{0,number,integer}` vẫn chỉ vào `arguments[0]`. Nếu có `{1}` bên trong nhánh thì nó vẫn lấy `arguments[1]` từ cùng mảng, không phải đối số đầu tiên của nhánh con.

### Lặp index và dùng nhiều index trong nhánh

Ví dụ khác:

~~~text
Status: {0,choice,0#empty|1#one item for {1}|1<{0,number,integer} items for {1}}
~~~

Với `new Object[]{3, "Lan"}`, kết quả là:

~~~text
Status: 3 items for Lan
~~~

Trong nhánh cuối, `{0,number,integer}` và `{1}` được xử lý sau khi `choice` chọn văn bản của nhánh đó. Đây là mô hình “lồng” đáng nhớ của `MessageFormat` và `ChoiceFormat`.

## 5. Mẫu con được parse lại; dữ liệu đối số thì không

Hai đoạn sau nhìn giống nhau nhưng có ý nghĩa khác nhau.

**Tình huống A:** `ChoiceFormat` trả một chuỗi có `{1}`, và `MessageFormat` dùng chuỗi đó như **mẫu lồng**.

**Tình huống B:** `ChoiceFormat` trả cùng chuỗi nhưng ứng dụng đưa nó làm **giá trị đối số `{0}`** cho một `MessageFormat` khác. Khi đó `{1}` bên trong giá trị được xem là **dữ liệu**, không tự parse tiếp.

Tạo **`NestedVersusDataDemo.java`**:

~~~java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class NestedVersusDataDemo {
    public static void main(String[] args) {
        ChoiceFormat choice =
                new ChoiceFormat("0#none|1#one|1<many {1}");

        String selected = choice.format(3);
        System.out.println(selected);

        MessageFormat asData =
                new MessageFormat("Status: {0}", Locale.US);
        System.out.println(asData.format(new Object[]{selected}));

        MessageFormat nested = new MessageFormat(
                "Status: {0,choice,0#none|1#one|1<many {1}}",
                Locale.US
        );
        System.out.println(nested.format(new Object[]{3, "X"}));
    }
}
~~~

~~~bash
javac NestedVersusDataDemo.java
java NestedVersusDataDemo
~~~

Kết quả:

~~~text
many {1}
Status: many {1}
Status: many X
~~~

Giải thích:

- `choice.format(3)` chỉ tạo văn bản `many {1}`.
- `asData.format(new Object[]{selected})` **chèn nguyên giá trị chuỗi**; nó không hiểu `{1}` bên trong đối số là placeholder cần thay.
- `nested.format(new Object[]{3, "X"})` chạy cơ chế choice **bên trong MessageFormat**; nhánh `many {1}` được format tiếp và nhận `X`.

Hệ quả tích cực: dữ liệu người dùng chứa `{0}` thường không biến thành mã pattern nếu được truyền đúng cách dưới dạng **argument**. Hệ quả nguy hiểm: nếu ứng dụng tự xây một pattern mới từ dữ liệu đó rồi parse lại, dữ liệu có thể được hiểu thành cú pháp. Hãy tách **mẫu được tin cậy** khỏi **giá trị động**.

## 6. Dấu nháy đơn là escape của `MessageFormat`

Khi `MessageFormat` parse pattern, dấu nháy đơn `'` có ý nghĩa đặc biệt:

- `''` trong pattern biểu diễn **một dấu nháy đơn literal**.
- `'{0}'` khiến `{0}` trở thành **văn bản literal**, không chèn đối số.
- `''{0}''` hiển thị **dấu nháy đơn quanh giá trị đã chèn**.

Đây **không** phải cú pháp Java dùng để tạo chuỗi. Những dấu `'` nằm **trong giá trị pattern tại runtime** được `MessageFormat` diễn giải.

Ví dụ runnable **`MessageQuoteDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        MessageFormat apostrophe =
                new MessageFormat("It''s {0}.", Locale.US);
        MessageFormat literal =
                new MessageFormat("Use '{0}' then {0}.", Locale.US);
        MessageFormat quotedValue =
                new MessageFormat("Value: ''{0}''.", Locale.US);

        System.out.println(apostrophe.format(new Object[]{"ready"}));
        System.out.println(literal.format(new Object[]{"X"}));
        System.out.println(quotedValue.format(new Object[]{"X"}));
    }
}
~~~

~~~bash
javac MessageQuoteDemo.java
java MessageQuoteDemo
~~~

Kết quả:

~~~text
It's ready.
Use {0} then X.
Value: 'X'.
~~~

Trong ngôn ngữ tự nhiên, dấu apostrophe như trong `It's`, `don't`, `l'utilisateur` thường là nguồn lỗi. Với pattern được xử lý bởi `MessageFormat`, viết `It''s`, `don''t`, `l''utilisateur` khi muốn chúng xuất hiện đúng.

**Lỗi thường gặp:** viết `"Value: '{0}'"` rồi mong nhìn thấy `'X'`. Trong `MessageFormat`, mẫu đó hiển thị `Value: {0}` do `{0}` đã bị quote thành literal.

## 7. Dấu ngoặc nhọn: không escape bằng backslash

Trong `MessageFormat`:

~~~text
'{0}'        → văn bản {0}
{0}          → giá trị đối số thứ nhất
''{0}''      → dấu ' + giá trị đối số + dấu '
~~~

Dấu backslash `\` **không** phải cơ chế quote placeholder. Nếu viết `\{0}` trong một pattern runtime, dấu backslash không ngăn `{0}` được hiểu là phần thay thế.

Cách đúng để hiển thị nguyên văn một chuỗi có ngoặc nhọn như `{name}` là quote đoạn chứa ngoặc theo **luật dấu nháy đơn của `MessageFormat`**, ví dụ:

~~~text
Pattern:  Please type '{name}' exactly.
Output:   Please type {name} exactly.
~~~

Không cố tạo một placeholder có tên `name` rồi truyền đối số với khóa đó: `java.text.MessageFormat` dùng **index dạng số**, không hỗ trợ `{name}` như một tham chiếu được đặt tên.

Khi một chuỗi có nhiều cặp ngoặc hoặc dấu apostrophe, nên viết test dựa trên **pattern runtime cuối cùng**. Nhìn vào mã nguồn Java hoặc file `.properties` mà bỏ qua tầng đọc đầu tiên dễ dẫn đến đếm nhầm ký tự escape.

## 8. Escape trong Java string literal và escape trong `MessageFormat`

Khi pattern được viết trực tiếp trong Java, trước hết Java compiler phải xử lý string literal.

Ví dụ:

~~~java
String pattern = "It''s {0}";
~~~

Chuỗi runtime vẫn chứa `It''s {0}`; dấu nháy đơn không cần escape bằng backslash trong **string literal có dấu nháy kép** của Java. Nhưng khi pattern đi qua `MessageFormat`, hai dấu nháy đơn được xử lý thành một dấu nháy đơn hiển thị.

So sánh:

| Java source | Chuỗi runtime trước khi format | `MessageFormat` với đối số `X` |
| --- | --- | --- |
| `"Hi {0}"` | `Hi {0}` | `Hi X` |
| `"It''s {0}"` | `It''s {0}` | `It's X` |
| `"'{0}'"` | `'{0}'` | `{0}` |
| `"''{0}''"` | `''{0}''` | `'X'` |
| `"A\n{0}"` | Hai dòng: `A` rồi `{0}` | Hai dòng: `A` rồi `X` |

Trong ví dụ `"A\n{0}"`, ký hiệu `\n` được **Java compiler** chuyển thành ký tự xuống dòng trước khi `MessageFormat` nhận pattern.

Dấu nháy kép `"` trong Java source cần được escape theo luật Java nếu muốn nằm trong string literal; dấu ngoặc nhọn `{` không phải escape của Java string. Đừng dùng `\\'` trong Java string để “sửa” cách `MessageFormat` diễn giải apostrophe: dấu backslash dành cho tầng Java không thay thế `''` dành cho tầng pattern.

### Cách kiểm tra khi khó phân biệt

Ghi lại hoặc debug chuỗi **sau khi Java đã tạo string** và **trước khi đưa cho `MessageFormat`**. Nếu chuỗi runtime đã không giống điều mong đợi, lỗi nằm ở tầng string literal. Nếu runtime pattern đúng nhưng đầu ra mất apostrophe hoặc in nguyên `{0}`, kiểm tra cú pháp `MessageFormat`.

## 9. Escape trong `.properties` khác escape của `MessageFormat`

Khi đặt bản dịch trong tệp `.properties`, có **hai phép biến đổi kế tiếp**:

~~~text
Nội dung file .properties
    → PropertyResourceBundle / properties parser
Chuỗi pattern runtime
    → MessageFormat parser
Chuỗi kết quả
~~~

Ví dụ **`Messages_en.properties`**:

~~~properties
success=It''s ready, {0}.
literal=Type '{0}' then enter {1}.
line=First line\nSecond line: {0}
~~~

Các ý cần nhớ:

- `It''s` dùng **hai dấu nháy đơn** vì quy tắc **MessageFormat**, không phải vì parser properties yêu cầu.
- `'{0}'` được giữ dưới dạng pattern và `MessageFormat` sẽ in `{0}` nguyên văn.
- `\n` trong `.properties` là escape tạo **ký tự xuống dòng** sau khi parser đọc file; `MessageFormat` nhận một chuỗi đã có xuống dòng.
- Trong `.properties`, dấu backslash cần được viết `\\` nếu muốn giữ một dấu backslash literal sau khi đọc. Một dấu backslash trước ký tự không được đặc tả có thể bị parser loại bỏ mà không giữ nguyên ký tự đó.

Tạo **`PropertiesMessageDemo.java`** và đặt cùng thư mục với file `Messages_en.properties`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class PropertiesMessageDemo {
    public static void main(String[] args) {
        Locale locale = Locale.ENGLISH;
        ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

        String success = bundle.getString("success");
        String literal = bundle.getString("literal");
        String line = bundle.getString("line");

        System.out.println(new MessageFormat(success, locale)
                .format(new Object[]{"Lan"}));
        System.out.println(new MessageFormat(literal, locale)
                .format(new Object[]{"ignored", "X"}));
        System.out.println(new MessageFormat(line, locale)
                .format(new Object[]{"done"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PropertiesMessageDemo.java
java -cp . PropertiesMessageDemo
~~~

Đầu ra:

~~~text
It's ready, Lan.
Type {0} then enter X.
First line
Second line: done
~~~

Chú ý thứ tự: file chứa `\n` **hai ký tự** backslash + chữ `n`, nhưng output chứa một dấu xuống dòng vì tầng parser của properties xử lý nó trước. Mã nguồn Java không chứa `\n` tương ứng cho giá trị này.

`ResourceBundle` có thể fallback sang bản dịch khác nếu thiếu bundle/khóa; khi xử lý lỗi escape, hãy xác nhận **bundle nào thực sự được chọn** và **chuỗi pattern runtime** là gì. Tránh “sửa” một file chưa từng được ứng dụng tải.

## 10. JSON và các định dạng vận chuyển không dùng cùng luật

Nếu thông điệp được lưu dưới dạng JSON, JSON parser cũng xử lý chuỗi trước khi `MessageFormat` nhìn thấy nó:

~~~json
{
  "message": "It''s {0}.",
  "twoLines": "First line\nSecond line: {0}"
}
~~~

Trong JSON, `\n` biểu diễn xuống dòng; trong chuỗi được parse, ký tự đó không còn là hai ký tự backslash + `n`. Cú pháp `''` không có ý nghĩa riêng với JSON; nó trở nên đặc biệt **chỉ khi chuỗi được đưa vào `MessageFormat`**.

Nếu chuỗi được nhúng vào thêm một literal Java để tạo ra JSON, lại có một tầng escape **trước JSON parser**. Không nên đếm số backslash theo cảm tính: hãy lần từng bước từ nguồn tới pattern runtime.

Không nhầm cú pháp Java `MessageFormat` với thư viện ICU MessageFormat hoặc cú pháp ICU plural:

~~~text
{count, plural, one {...} other {...}}
~~~

Đây **không** phải cú pháp plural mà `java.text.MessageFormat` chuẩn của Java 17 chấp nhận. Để dùng ICU plural, cần dùng formatter/thư viện có parser ICU tương ứng; `ChoiceFormat` trong JDK sử dụng ngưỡng và luật khác. Dán ICU pattern nguyên vẹn vào `new java.text.MessageFormat(...)` có thể gây lỗi parse.

## 11. Mẫu con và apostrophe: vì sao phải xét nhiều lần parse?

`MessageFormat` nhận pattern ngoài. Khi chọn một nhánh `choice` có nội dung giống pattern, nó có thể tạo và dùng một `MessageFormat` khác để format **chuỗi nhánh**. Điều này sinh ra thêm **một tầng diễn giải dấu nháy đơn và dấu ngoặc nhọn**.

Ví dụ:

~~~text
{0,choice,0#none|1#one|1<{0,number,integer} items}
~~~

Trong nhánh cuối, `{0,number,integer}` không phải văn bản cố định; nó được parse thành placeholder khi nhánh được format lại.

Nếu muốn đoạn nhánh chứa **dấu nháy đơn literal**, hoặc **ngoặc nhọn literal**, phải xét hai bộ parser: pattern bên ngoài (bao gồm xử lý dấu nháy đơn) và pattern nhánh được chọn. Số lượng apostrophe cần viết có thể khác khi mẫu nằm trong `.properties`, chuỗi Java, hay chuỗi đã được tạo bởi code.

**Không có quy tắc ngắn “luôn nhân đôi dấu nháy đúng một lần là đủ” cho mọi mức lồng.** Quy tắc tốt hơn:

1. Viết ra **chuỗi đầu ra mong muốn**.
2. Xác định placeholder nào phải được xử lý ở **mẫu con**.
3. Viết mẫu con hợp lệ cho parser của nó và thử độc lập nếu có thể.
4. Xây pattern ngoài; xác định ký tự quote nào sẽ bị parser ngoài xử lý.
5. Sau cùng, encode pattern ngoài theo nguồn lưu trữ: Java literal, `.properties` hoặc JSON.
6. Kiểm thử với **mọi nhánh choice**, đặc biệt những nhánh không được kích hoạt bởi dữ liệu thử thông thường.

Việc chỉ kiểm thử nhánh `0#...` rồi coi cả pattern an toàn là không đủ: lỗi ở nhánh `1<...` có thể chỉ bộc lộ khi số lượng thực tế vượt 1.

### Tránh lồng nhiều tầng khi khó bảo trì

Nếu mức lồng tăng nhanh và việc quote trở nên khó đọc, ứng dụng có thể:

- Dùng những **message key riêng cho từng nhánh** rồi format mỗi message đúng một lần.
- Chọn nhánh bằng code có test rõ, truyền dữ liệu động làm **đối số** thay vì nối chuỗi pattern.
- Dùng thư viện hỗ trợ plural/ngữ pháp phù hợp với các ngôn ngữ sản phẩm phục vụ.

Mục tiêu là biểu diễn đúng ngữ pháp và dễ xác minh, không phải tối đa hóa độ sâu lồng `ChoiceFormat`.

## 12. Lỗi đặc biệt: chuỗi do người dùng cung cấp bị parse như pattern

Giả sử người dùng nhập văn bản:

~~~text
Hello {1}
~~~

**Nếu truyền làm argument**, `MessageFormat` coi đây là dữ liệu:

~~~java
MessageFormat formatter =
        new MessageFormat("Comment: {0}", Locale.US);
System.out.println(formatter.format(new Object[]{"Hello {1}"}));
~~~

Đoạn này đặt trong method có import `java.text.MessageFormat` và `java.util.Locale`. Kết quả:

~~~text
Comment: Hello {1}
~~~

Không có vòng parse thứ hai cho nội dung đối số theo cách dùng thông thường này.

**Nếu nối vào pattern**:

~~~java
String userInput = "Hello {1}";
String pattern = "Comment: " + userInput + " / {0}";
MessageFormat formatter = new MessageFormat(pattern, Locale.US);
~~~

`{1}` trong dữ liệu đã được đưa vào **cú pháp pattern**; kết quả có thể bị thay, giữ nguyên do thiếu đối số, hoặc làm hỏng mẫu nếu văn bản khác chứa ký tự đặc biệt. Vì vậy **không xây pattern bằng dữ liệu chưa được kiểm soát**.

Đối với các giá trị dùng trong nested choice, sự chú ý càng quan trọng: một nhánh được parse lại có thể biến ký tự `{...}` thành placeholder nếu chúng thuộc **pattern** của nhánh. Giữ pattern do ứng dụng hoặc hệ thống dịch đáng tin cậy quản lý, và giữ nội dung người dùng trong arguments.

Điều này chỉ xử lý ranh giới **cú pháp MessageFormat**. Khi kết quả được đặt vào HTML, URL, SQL hoặc template khác, vẫn cần xử lý an toàn của **đích đó**. `MessageFormat` không tự encode HTML hay thay thế prepared statement.

## 13. HTML escape và MessageFormat escape là hai vấn đề

Giả sử đầu ra sau format là:

~~~text
Hello <script>alert(1)</script>
~~~

Với `MessageFormat`, dấu `<` và `>` là ký tự văn bản bình thường. Nếu đưa chuỗi trên vào `innerHTML` mà không xử lý, trình duyệt có thể diễn giải HTML do người dùng cung cấp.

Để hiển thị **văn bản**, giao diện nên dùng API gán text, ví dụ `textContent` trên web, hoặc HTML-encode đúng **ngữ cảnh output** nếu bắt buộc sinh HTML. Không tự thay tất cả dấu apostrophe/ngoặc nhọn của MessageFormat rồi nghĩ rằng đã đạt an toàn HTML.

| Ký tự / cú pháp | Tầng liên quan | Cách hiểu |
| --- | --- | --- |
| `{0}` | `MessageFormat` | Thay đối số 0 |
| `'{0}'` | `MessageFormat` | In `{0}` nguyên văn |
| `&lt;` | HTML text | Biểu diễn dấu `<` khi render HTML |
| `\"` trong JSON string | JSON parser | Tạo dấu nháy kép trong giá trị string |
| `\\` trong `.properties` | Properties parser | Giữ một dấu backslash literal sau khi đọc |
| `<script>` trong argument | Giao diện đầu ra | Không được coi là HTML an toàn chỉ vì đã đi qua MessageFormat |

Cú pháp escape đúng ở **một tầng** không thay thế việc escape ở **tầng khác**.

## 14. Số nhiều và ngữ pháp: giới hạn của `ChoiceFormat`

Ví dụ với ba nhánh 0, 1, nhiều cho tiếng Anh rất dễ hiểu, nhưng chưa đủ để hỗ trợ quy tắc số nhiều toàn cầu.

Một số ngôn ngữ có dạng số nhiều khác nhau cho 0, 1, 2, các nhóm số như 3–10, số kết thúc bằng 1 hoặc số thập phân. `ChoiceFormat` dựa trên **ngưỡng số**, nên phải lập nhiều nhánh và vẫn có thể không biểu diễn đúng mọi quy tắc plural theo CLDR.

Do đó:

- Đừng xem `0#...|1#...|1<...` là thuật toán số nhiều đúng cho mọi locale.
- Không nhầm `{0,number,integer}` với việc chọn **hình thái từ** theo số lượng; nó chỉ định dạng con số.
- Với sản phẩm nhiều ngôn ngữ, cân nhắc công cụ i18n hiểu **plural categories** của từng ngôn ngữ và kiểm thử dữ liệu `0`, `1`, `2`, `5`, `11`, `21`, số âm và thập phân tùy ngôn ngữ.
- Khi dùng thư viện khác JDK, phải dùng **parser và quy tắc escaping của thư viện đó**, không áp dụng mặc định `ChoiceFormat` của Java vào ICU message.

Một chuỗi có thể **đúng cú pháp** nhưng **sai ngữ pháp**. Việc format thành công không chứng minh bản dịch tự nhiên ở mọi locale.

## 15. Kiểm thử escape và nested messages

Nên lập bộ test từ **các chuỗi cuối cùng**, không chỉ kiểm tra pattern trông có vẻ đúng.

| Tình huống | Kiểm tra |
| --- | --- |
| `choice` với 0, 1, 2, 5 | Đúng nhánh và đúng ngữ pháp ở miền dữ liệu cần hỗ trợ |
| Mẫu con chứa `{0}` hoặc `{1}` | Dùng đúng mảng arguments ở lần parse lồng |
| Cùng chuỗi `{1}` truyền làm argument | Giữ nguyên như dữ liệu, không bị parse như pattern |
| `It's` / `don't` | Dấu apostrophe xuất hiện đúng |
| `'{0}'` / `''{0}''` | Phân biệt placeholder literal và giá trị có dấu nháy |
| `.properties` chứa `\n` | Có xuống dòng thật sau khi đọc tài nguyên |
| JSON chứa `\n` | Parser JSON xử lý escape trước formatter |
| Mẫu sai hoặc thiếu đối số | Không để `{1}` xuất hiện trong UI do hợp đồng dữ liệu sai |
| Nâng JDK/provider | Xem xét thay đổi localized number/date, khoảng trắng và quy tắc hiển thị |
| Đầu ra HTML có nội dung động | Encode theo HTML context, không dựa vào MessageFormat |

### Kiểm thử độc lập các nhánh

Khi dùng `ChoiceFormat`, đừng chỉ test một số “đại diện” mà bỏ qua ranh giới. Với `0#none|1#one|1<many`, tối thiểu thử `0`, `1`, `2` và các giá trị ngoài miền dữ liệu nếu API có thể nhận chúng.

Nếu một nhánh con chứa placeholder mới `{2}` nhưng code chỉ truyền hai đối số, output có thể còn nguyên `{2}`. Nên phát hiện từ kiểm thử contract về **tập chỉ số và ý nghĩa từng chỉ số**, thay vì hy vọng formatter luôn báo lỗi.

### Kiểm thử literal apostrophe ở nhiều nguồn

Một thông điệp tiếng Anh giống nhau, ví dụ “It's ready, Lan.”, khi lưu ở Java string literal, `.properties` và JSON có thể được viết khác nhau ở phần backslash, nhưng **pattern runtime sau khi decode** cần giữ chuỗi `It''s ready, {0}.`. Sau đó `MessageFormat` mới chuyển thành đầu ra có một apostrophe.

Đừng dùng regex thay thế `'` hoặc `{...}` theo kiểu toàn cục trên tệp dịch mà không hiểu thứ tự parser; có thể làm hỏng những mẫu đã quote đúng.

## 16. Các ngộ nhận phổ biến

1. **“`ChoiceFormat` tự xử lý số nhiều theo CLDR.”** Không: nó chọn nhánh theo giới hạn số, không phải engine plural rules đa ngôn ngữ.
2. **“Mọi chuỗi trả về có `{1}` sẽ được `MessageFormat` parse lại.”** Không: chuỗi đi vào dưới dạng argument là dữ liệu; mẫu con được chọn từ `choice` bên trong `MessageFormat` có cơ chế riêng.
3. **“Dấu backslash escape được dấu ngoặc nhọn của MessageFormat.”** Không: dùng quy tắc dấu nháy đơn của pattern.
4. **“Viết `'{0}'` sẽ in dấu nháy quanh đối số.”** Sai: nó in literal `{0}`; cần `''{0}''` để in `'X'`.
5. **“Đặt pattern trong file properties thì không cần quote apostrophe.”** Sai nếu pattern được đưa qua `MessageFormat`; properties parser không thay thế quy tắc của formatter.
6. **“Escape được trong Java source thì chắc chắn đúng khi qua MessageFormat.”** Sai: đó là hai parser nối tiếp.
7. **“JSON và Java MessageFormat dùng chung cú pháp plural.”** Sai: JSON chỉ đóng vai trò định dạng chứa chuỗi; `MessageFormat` quyết định cú pháp của pattern bên trong.
8. **“Lồng thêm một vòng format luôn an toàn và không đổi ý nghĩa.”** Sai: chuỗi chứa dấu ngoặc hoặc apostrophe có thể bị parse lại thành cú pháp.
9. **“MessageFormat tự chống XSS khi hiển thị HTML.”** Sai: cần encode output theo HTML context.
10. **“Một nhánh chạy đúng là toàn bộ pattern đúng.”** Sai: nhánh chưa chọn có thể có placeholder thiếu hoặc logic ngữ pháp sai.

## 17. Quy trình áp dụng trong ứng dụng thực tế

1. **Xác định nguồn pattern** (Java source, `.properties`, JSON hoặc catalog của thư viện i18n) và parser đầu tiên xử lý nguồn đó.
2. **Xác định hợp đồng đối số**: index 0 đại diện điều gì, index 1 đại diện điều gì, kiểu dữ liệu dự kiến là gì.
3. **Thiết kế các nhánh** theo nhu cầu ngữ pháp thực tế. Dùng `ChoiceFormat` cho bài toán ngưỡng phù hợp; với plural phức tạp, chọn công cụ có dữ liệu plural theo locale.
4. **Viết pattern runtime**, rồi escape theo **MessageFormat** (apostrophe, braces) và theo **parser của nguồn lưu trữ**.
5. **Nếu có mẫu con**, thử phần được chọn độc lập và sau đó thử pattern đầy đủ để phát hiện lỗi parse lồng.
6. **Truyền locale tường minh** khi format số/ngày; không đổi default JVM trên mỗi request.
7. **Truyền dữ liệu người dùng dưới dạng arguments**, tránh nối dữ liệu vào pattern; encode kết quả theo nơi hiển thị.
8. **Kiểm thử mọi nhánh và locale được sản phẩm hỗ trợ**, nhất là dấu nháy đơn, ngoặc nhọn literal, số lượng biên và các tầng escape.

### Tự kiểm tra

**Câu 1.** Tại sao `Status: many {1}` vẫn có thể xuất hiện nguyên văn khi đưa `many {1}` làm đối số cho `MessageFormat("Status: {0}")`?

**Đáp án:** `{1}` nằm **trong dữ liệu đối số**, nên không bị parse thành placeholder.

**Câu 2.** Vì sao `{1}` ở nhánh `1<many {1}` của một `choice` lồng trong `MessageFormat` lại có thể trở thành `X`?

**Đáp án:** Đoạn nhánh được chọn được xử lý như **pattern lồng** và dùng cùng mảng đối số.

**Câu 3.** Muốn in `It's ready.` từ `MessageFormat`, cần viết gì trong pattern runtime?

**Đáp án:** `It''s ready.` — hai apostrophe để tạo một apostrophe hiển thị.

**Câu 4.** Dùng `\{0}` để in `{0}` nguyên văn có đúng không?

**Đáp án:** Không. Trong `MessageFormat` dùng `'{0}'` ở pattern runtime.

**Câu 5.** Một chuỗi đã escape đúng cho `MessageFormat` có thể đưa thẳng vào HTML không?

**Đáp án:** Không nhất thiết. Vẫn phải encode nội dung theo ngữ cảnh HTML hoặc dùng API hiển thị text phù hợp.

**Ghi nhớ:** **Lồng thông điệp là lồng những lần diễn giải pattern; escape phải đúng ở từng tầng.** Phân biệt chuỗi nguồn, pattern runtime, nhánh `choice` được format tiếp, dữ liệu đối số và ngữ cảnh hiển thị cuối cùng. Khi các tầng được phân định rõ, việc viết và kiểm thử bản dịch nhiều ngôn ngữ sẽ đáng tin cậy hơn.