# Các đoạn chữ có hướng khác nhau và mức nhúng trong Java

## 1. Vấn đề: một dòng có thể chứa nhiều hướng chữ

Trong giao diện quốc tế, không phải mọi văn bản đều được đọc từ trái sang phải (**LTR, left-to-right**). Tiếng Việt, tiếng Anh và phần lớn chữ Latin thường có hướng LTR; tiếng Hebrew và tiếng Ả Rập thường có hướng **RTL, right-to-left**. Một câu có thể chứa cả hai, xen với số, dấu câu, mã sản phẩm hoặc liên kết URL:

~~~text
abc אבג 123 xyz
~~~

Chuỗi trên được viết ở đây theo **thứ tự logic** (*logical order*) của các ký tự: `a b c`, một dấu cách, ba chữ Hebrew, dấu cách, `1 2 3`, dấu cách, `x y z`. Trên giao diện hỗ trợ Unicode Bidirectional Algorithm (**UBA**), các phần tử có thể xuất hiện theo **thứ tự thị giác** (*visual order*) khác với thứ tự được lưu. Vị trí của các dấu câu, ngoặc và số còn phụ thuộc **hướng nền của đoạn văn**, các ký tự liền kề và những dấu điều khiển hướng được cung cấp.

Java có API chuẩn `java.text.Bidi` để **phân tích hướng và mức nhúng** (*embedding levels*) cho văn bản hai chiều, và các API Java2D như `TextLayout` để hỗ trợ bố trí/hiển thị. Bài học tập trung vào việc hiểu **đoạn chữ có hướng khác nhau**, **mức nhúng**, **hướng đoạn văn**, cách kiểm tra bằng Java và ứng dụng an toàn trong giao diện.

**Ghi nhớ từ đầu:** không tự đảo `String` để hiển thị tiếng Hebrew/Ả Rập. Hãy **giữ dữ liệu theo thứ tự logic** và sử dụng thành phần hiển thị có hỗ trợ bidi cùng chính sách hướng phù hợp.

## 2. Logical order và visual order là hai khái niệm khác nhau

| Khái niệm | Ý nghĩa | Ví dụ ứng dụng |
| --- | --- | --- |
| **Logical order** | Thứ tự ký tự được lưu trong chuỗi và được duyệt theo chỉ số | `String`, dữ liệu database, kết quả copy/paste |
| **Visual order** | Thứ tự các đoạn/ký tự được bố trí từ trái sang phải trên dòng hiển thị sau thuật toán bidi | Bố cục trong GUI, trình duyệt, PDF renderer |
| **Base direction** | Hướng nền của một đoạn văn (*paragraph*), thường LTR hoặc RTL | Đoạn chat tiếng Anh so với đoạn chat tiếng Ả Rập |
| **Directional run** | Khoảng liên tiếp có cùng mức bidi đã phân giải | Một phần Latin, một phần Hebrew, một cụm số |
| **Embedding level** | Số nguyên thể hiện hướng chẵn/lẻ và ngữ cảnh lồng bên trong | Mức `0`, `1`, `2` trong cùng dòng |
| **Isolation** | Cách tách một phần văn bản khỏi tác động định hướng của nội dung xung quanh | Chèn tên người dùng chưa biết ngôn ngữ vào câu |
| **Glyph shaping** | Biến ký tự thành hình glyph, nối nét, chọn dạng chữ theo phông | Các dạng liên kết chữ Ả Rập |

Ba lớp thao tác cần tách:

1. **Dữ liệu**: giữ thứ tự code point logic, nội dung và định danh.
2. **Bidi layout**: xác định các đoạn và thứ tự sắp xếp theo hướng.
3. **Rendering**: vẽ glyph, chọn font, shaping, vị trí dấu, con trỏ và hit testing.

`java.text.Bidi` cung cấp thông tin ở lớp 2; bản thân nó **không phải** API vẽ chữ Ả Rập hoàn chỉnh. Đảo `String` hay đảo từng `char` không giải quyết được shaping, dấu kết hợp, cụm emoji, ngoặc hoặc vị trí con trỏ.

## 3. Unicode Bidirectional Algorithm phân loại ký tự như thế nào?

UBA không chỉ hỏi “đây là tiếng nào?”. Nó dùng **thuộc tính hướng của từng ký tự**, ngữ cảnh và các quy tắc giải quyết hướng.

Những nhóm đáng biết:

| Loại hướng | Ví dụ | Vai trò |
| --- | --- | --- |
| Strong LTR | Chữ Latin `a`, `b`, `c` | Cung cấp hướng mạnh LTR |
| Strong RTL | Nhiều ký tự Hebrew, Ả Rập | Cung cấp hướng mạnh RTL |
| Số/weak | Các chữ số `0–9` và một số dấu phân cách số | Có các quy tắc riêng; không đơn giản “RTL vì nằm trong câu RTL” |
| Neutral | Khoảng trắng, nhiều dấu ngoặc và dấu câu | Hướng biểu kiến có thể bị chi phối bởi phần lân cận |
| Explicit formatting | `RLE`, `LRE`, `RLO`, `LRO`, `PDF`, isolates | Thay đổi ngữ cảnh hướng hoặc cách cô lập theo UBA |

Java cung cấp `Character.getDirectionality(int codePoint)` và các hằng `Character.DIRECTIONALITY_*` để kiểm tra **loại hướng Unicode** của từng code point. Nhưng **thuộc tính của một ký tự không phải mức nhúng cuối cùng**: `Bidi` còn phải áp dụng quy tắc cho toàn đoạn.

Ví dụ một số `123` nằm giữa chữ Hebrew có thể nhận mức **chẵn** để các chữ số vẫn có trình tự đọc hợp lý, trong khi phần chữ RTL có mức **lẻ**. Dấu cách ở ranh giới có thể thuộc đoạn khác với điều người mới học dự đoán.

### Hướng đoạn văn và ký tự mạnh đầu tiên

Thuật toán cần xác định hướng nền của đoạn. Có hai cách phổ biến:

- **Đặt hướng nền tường minh** bằng metadata của giao diện (ví dụ trường nhập RTL/LTR) hoặc tham số `Bidi`.
- **Để thuật toán suy đoán** từ ký tự mạnh đầu tiên; nếu không có ký tự mạnh, dùng hướng fallback.

Đừng suy hướng toàn đoạn chỉ từ ngôn ngữ của vài từ cuối câu. Một đoạn có ký tự mạnh Latin đầu tiên có thể được suy nền LTR ngay cả khi phía sau có phần RTL dài.

## 4. Mức nhúng: số chẵn là LTR, số lẻ là RTL

`Bidi` giải quyết mức nhúng cho các đoạn ký tự. Quy tắc trực quan:

- **Mức chẵn**: hướng LTR, ví dụ `0`, `2`, `4`.
- **Mức lẻ**: hướng RTL, ví dụ `1`, `3`, `5`.
- Mức lớn hơn có nghĩa đoạn nằm trong ngữ cảnh hướng/lồng phức tạp hơn; nó **không** phải số lượng ký tự hay số lần code gọi `String.substring`.
- Hướng nền thường tương ứng mức `0` cho đoạn nền LTR hoặc `1` cho đoạn nền RTL.

Ví dụ mức `2` có thể xuất hiện cho **cụm số LTR** bên trong vùng RTL mức `1`. Do đó một dòng nhìn như chỉ có hai ngôn ngữ vẫn có **nhiều hơn hai mức**.

**Đừng nhầm:** không phải cứ gặp từ RTL là tạo “mức 1” và cứ gặp số là “mức 2” trong mọi trường hợp. Mức thực tế được tính từ toàn bộ ngữ cảnh bidi, hướng nền và điều khiển định hướng; các giá trị trên chỉ là tình huống phổ biến.

### Run trong Bidi là gì?

Một **level run** là khoảng liên tiếp có mức đã phân giải giống nhau. `java.text.Bidi` có những phương thức:

| API | Ý nghĩa |
| --- | --- |
| `getBaseLevel()` | Mức nền của đoạn: thường `0` hoặc `1` |
| `baseIsLeftToRight()` | Kiểm tra hướng nền LTR |
| `isLeftToRight()` | Đoạn hoàn toàn LTR với nền LTR |
| `isRightToLeft()` | Đoạn hoàn toàn RTL với nền RTL |
| `isMixed()` | Có hỗn hợp hướng cần xử lý |
| `getRunCount()` | Số đoạn có mức liên tiếp |
| `getRunStart(i)` | Chỉ số đầu của run thứ `i`, bao gồm |
| `getRunLimit(i)` | Chỉ số kết thúc **không bao gồm** của run |
| `getRunLevel(i)` | Mức nhúng của run |
| `getLevelAt(index)` | Mức đã phân giải tại vị trí ký tự |
| `getLength()` | Độ dài đoạn được phân tích |

**Chỉ số của Java `Bidi` dựa trên vị trí ký tự UTF-16**, giống `String.substring(start, end)`. Nếu chuỗi có ký tự ngoài BMP (ví dụ emoji), một code point có thể chiếm **hai code unit**, nên không dùng chỉ số run như số thứ tự grapheme nhìn thấy.

## 5. Ví dụ chạy được: xem run và mức nhúng trong Java 17+

Tạo file `BidiRunsDemo.java`:

~~~java
import java.text.Bidi;

public class BidiRunsDemo {
    public static void main(String[] args) {
        // abc + một từ Hebrew + số + xyz, theo thứ tự logic.
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";

        Bidi bidi = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);

        System.out.println("Length: " + text.length());
        System.out.println("Base level: " + bidi.getBaseLevel());
        System.out.println("Mixed: " + bidi.isMixed());
        System.out.println("Runs: " + bidi.getRunCount());

        for (int i = 0; i < bidi.getRunCount(); i++) {
            int start = bidi.getRunStart(i);
            int limit = bidi.getRunLimit(i);
            int level = bidi.getRunLevel(i);

            System.out.printf("Run %d: [%d,%d) level=%d %s%n",
                    i, start, limit, level,
                    level % 2 == 0 ? "LTR" : "RTL");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BidiRunsDemo.java
java BidiRunsDemo
~~~

Kết quả với thuật toán Java đã kiểm tra trên JDK:

~~~text
Length: 15
Base level: 0
Mixed: true
Runs: 4
Run 0: [0,4) level=0 LTR
Run 1: [4,8) level=1 RTL
Run 2: [8,11) level=2 LTR
Run 3: [11,15) level=0 LTR
~~~

Giải thích các đoạn theo **vị trí logic**:

- `[0,4)` gồm `abc` và dấu cách, mức 0 (LTR).
- `[4,8)` gồm ba ký tự Hebrew và dấu cách theo cách phân giải của ví dụ, mức 1 (RTL).
- `[8,11)` là `123`, mức 2 (LTR nằm trong ngữ cảnh RTL).
- `[11,15)` gồm dấu cách và `xyz`, mức 0.

Đây là bằng chứng quan trọng: **run có mức 2 hoàn toàn có thể nằm giữa các vùng LTR/RTL**, và run do `Bidi` cung cấp là **các khoảng theo thứ tự logic**. Không coi thứ tự trả về của `getRunStart` là sẵn **thứ tự hiển thị**.

Chú ý: chuỗi trong source dùng `\u05D0\u05D1\u05D2` thay vì gõ Hebrew trực tiếp để người đọc nhìn rõ code point và tránh nhầm thứ tự khi sao chép tài liệu. Java xử lý các escape này thành ký tự Hebrew tương ứng.

## 6. Hướng nền khác nhau có thể tạo mức khác nhau

`Bidi` hỗ trợ các tham số hướng đoạn:

| Hằng số | Chính sách |
| --- | --- |
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Chọn nền LTR |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Chọn nền RTL |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Suy hướng từ nội dung mạnh; khi không quyết định được thì ưu tiên LTR |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Suy hướng từ nội dung mạnh; khi không quyết định được thì ưu tiên RTL |

Đây là chính sách **cho đoạn**, không phải câu lệnh “biến mọi ký tự thành LTR” hay “đảo chuỗi”. Một đoạn nền RTL vẫn có thể chứa số và URL cần giữ trình tự LTR.

### Ví dụ chạy được: cùng chuỗi, hai hướng nền

Tạo `BidiBaseDirectionDemo.java`:

~~~java
import java.text.Bidi;

public class BidiBaseDirectionDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";

        Bidi ltr = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);
        Bidi rtl = new Bidi(
                text, Bidi.DIRECTION_RIGHT_TO_LEFT);

        System.out.println("LTR base: " + ltr.getBaseLevel());
        System.out.println("LTR run count: " + ltr.getRunCount());
        System.out.println("RTL base: " + rtl.getBaseLevel());
        System.out.println("RTL run count: " + rtl.getRunCount());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BidiBaseDirectionDemo.java
java BidiBaseDirectionDemo
~~~

Kết quả đã kiểm tra:

~~~text
LTR base: 0
LTR run count: 4
RTL base: 1
RTL run count: 5
~~~

Hai đối tượng phân tích **cùng dữ liệu logic**, nhưng phần dấu cách và các run ở ranh giới có thể được phân giải theo nền khác nhau. Với giao diện, nên đặt hướng nền theo **ngữ cảnh người dùng/loại trường**, không chỉ suy từ ký tự ngẫu nhiên đầu tiên nếu đã có thông tin chắc chắn.

### Hướng tự động có giới hạn

Các chế độ `DIRECTION_DEFAULT_*` hữu ích khi không biết hướng từ trước, nhưng một chuỗi bắt đầu bằng **mã sản phẩm Latin** rồi mới có câu tiếng Ả Rập có thể bị suy LTR. Ngược lại, khi văn bản chỉ gồm số và dấu trung tính, thuật toán cần fallback. Đó là lý do metadata hướng của trường/đoạn vẫn quan trọng.

## 7. Reordering: không được nhầm “phân tích run” với “vẽ chữ”

`Bidi.reorderVisually(byte[] levels, int levelStart, Object[] objects, int objectStart, int count)` có thể sắp lại **thứ tự các đối tượng** dựa trên mức đã tính, ví dụ các đoạn text được renderer quản lý.

### Ví dụ đầy đủ chỉ kiểm tra phép reorder

Lưu `BidiReorderDemo.java`:

~~~java
import java.text.Bidi;
import java.util.Arrays;

public class BidiReorderDemo {
    public static void main(String[] args) {
        Object[] runs = {"A", "B", "C"};
        byte[] levels = {0, 1, 2};

        Bidi.reorderVisually(levels, 0, runs, 0, runs.length);

        System.out.println(Arrays.toString(runs));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BidiReorderDemo.java
java BidiReorderDemo
~~~

Kết quả:

~~~text
[A, C, B]
~~~

Đây là ví dụ **đảo vị trí các object đại diện cho run**, không phải ví dụ vẽ glyph. `reorderVisually` **không tự shaping chữ Ả Rập**, không biến text logic thành một chuỗi thích hợp lưu database, và không có quyền thay đổi giá trị văn bản gốc.

### Những việc không nên tự làm

- `new StringBuilder(text).reverse()` để hiển thị câu RTL.
- Đảo cả chuỗi rồi đảo các từ Latin riêng.
- Đảo thứ tự code unit trong một grapheme, làm mất dấu kết hợp/emoji.
- Tự đảo nội dung số điện thoại, URL, thẻ số sản phẩm.
- Ghi text đã reorder về database như “bản đã địa phương hóa”.

UBA tính **bố cục cho một dòng**; trình hiển thị còn phải xử lý ngắt dòng, vị trí dấu ngoặc, shaping, phông và con trỏ. Thứ tự thị giác là kết quả trình bày, **không nên thành dữ liệu nguồn**.

## 8. Bidi của toàn đoạn và từng dòng sau khi ngắt dòng

Đoạn văn có thể được chia thành nhiều **dòng hiển thị** tùy chiều rộng vùng text, kích thước phông và thiết bị. Khi đó, việc reorder trực quan cần áp dụng theo **từng dòng**, không đơn giản reorder cả đoạn rồi cắt chuỗi theo số ký tự.

`Bidi.createLineBidi(int lineStart, int lineLimit)` tạo một đối tượng bidi cho khoảng dòng (các chỉ số tính từ đoạn đã phân tích). Đây là một bước hỗ trợ renderer.

### Ví dụ Java 17+ chạy được

Tạo `BidiLineDemo.java`:

~~~java
import java.text.Bidi;

public class BidiLineDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";
        Bidi paragraph = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);

        // Giả sử dòng thứ nhất chứa [0,11).
        Bidi line = paragraph.createLineBidi(0, 11);

        System.out.println("Line base: " + line.getBaseLevel());
        System.out.println("Line length: " + line.getLength());
        System.out.println("Line runs: " + line.getRunCount());

        for (int i = 0; i < line.getRunCount(); i++) {
            System.out.printf("[%d,%d) level=%d%n",
                    line.getRunStart(i),
                    line.getRunLimit(i),
                    line.getRunLevel(i));
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BidiLineDemo.java
java BidiLineDemo
~~~

Kết quả đã đối chiếu với JDK:

~~~text
Line base: 0
Line length: 11
Line runs: 3
[0,4) level=0
[4,8) level=1
[8,11) level=2
~~~

Chỉ số `[0,11)` ở đây là **ranh giới dòng giả định** để minh họa API. Trong một UI thật, line break phải được tính dựa trên chiều rộng render, font và quy tắc tách dòng; không tự chia dòng sau 11 code unit rồi xem đó là cách line breaking đúng cho mọi ngôn ngữ.

**Phân biệt hai bước:** phân tích bidi theo đoạn văn; khi layout thành nhiều dòng, renderer xử lý việc sắp xếp trực quan theo từng dòng dựa trên kết quả. Việc có một run chẵn/lẻ không tự cho biết glyph phải được vẽ ở pixel nào.

## 9. AttributedString, RUN_DIRECTION và BIDI_EMBEDDING

Java còn có mô hình văn bản có thuộc tính thông qua `AttributedString` và `java.awt.font.TextAttribute`. Đây là công cụ để các API văn bản/Java2D hiểu **hướng đoạn** và những yêu cầu nhúng tường minh.

Hai thuộc tính cần phân biệt:

| Thuộc tính | Vai trò |
| --- | --- |
| `TextAttribute.RUN_DIRECTION` | Đặt hướng nền của **toàn đoạn văn**; dùng `RUN_DIRECTION_LTR` hoặc `RUN_DIRECTION_RTL` |
| `TextAttribute.BIDI_EMBEDDING` | Cung cấp mức nhúng/override tường minh cho khoảng văn bản theo hợp đồng API |

`RUN_DIRECTION` nên có **cùng giá trị trong toàn đoạn**. Đặt nhiều giá trị khác nhau trong một đoạn có hành vi không xác định theo tài liệu Java, nên không dùng nó như “đổi hướng từng từ” bằng cách tô thuộc tính lên từng ký tự.

`BIDI_EMBEDDING` có thể dùng mức dương để nhúng hoặc mức âm để override. Nó là một cơ chế **nâng cao**; nên để UBA tự tính nếu không có yêu cầu layout cụ thể. Đặt mức sai có thể tạo kết quả khó đọc hoặc tăng bề mặt rủi ro spoofing.

### Ví dụ đầy đủ: chỉ định hướng nền RTL

Lưu `AttributedBidiDemo.java`:

~~~java
import java.awt.font.TextAttribute;
import java.text.AttributedString;
import java.text.Bidi;

public class AttributedBidiDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";
        AttributedString attributed = new AttributedString(text);

        attributed.addAttribute(
                TextAttribute.RUN_DIRECTION,
                TextAttribute.RUN_DIRECTION_RTL
        );

        Bidi bidi = new Bidi(attributed.getIterator());

        System.out.println("Attributed base: "
                + bidi.getBaseLevel());
        System.out.println("Mixed: " + bidi.isMixed());
        System.out.println("Runs: " + bidi.getRunCount());
    }
}
~~~

Biên dịch/chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 AttributedBidiDemo.java
java AttributedBidiDemo
~~~

Kết quả đã đối chiếu:

~~~text
Attributed base: 1
Mixed: true
Runs: 5
~~~

Đoạn này cho thấy `AttributedString` có thể mang thông tin **hướng nền RTL** mà không thay chuỗi nguồn. `TextAttribute` thuộc module Java Desktop (`java.desktop`) trong JDK đầy đủ; `java.text.Bidi` thuộc `java.base`.

### BIDI_EMBEDDING trong các đoạn nội bộ

Có thể chỉ rõ mức cho một khoảng khi renderer cần:

~~~java
AttributedString a = new AttributedString(text);
a.addAttribute(
        TextAttribute.BIDI_EMBEDDING,
        Integer.valueOf(2),
        from, to
);
~~~

Đây là **mảnh mã trong method**, với `text` kiểu `String` và `from/to` là offset UTF-16 hợp lệ, không phải class chạy độc lập. Cần import `java.text.AttributedString` và `java.awt.font.TextAttribute`.

**Đừng sử dụng bừa:** tài liệu `TextAttribute` lưu ý khi `BIDI_EMBEDDING` được đặt ở bất kỳ vị trí nào trong paragraph, các điều khiển Unicode dạng embedding/override truyền thống như `RLE/LRE/RLO/LRO/PDF` sẽ bị bỏ qua trong cơ chế thuộc tính đó; các run không có thuộc tính được coi như mức 0. Vì vậy trộn cả hai cơ chế mà không hiểu thứ tự ưu tiên có thể làm hỏng kết quả.

Nếu bạn đang viết giao diện bằng Swing, JavaFX hoặc HTML, ưu tiên **cơ chế hỗ trợ bidi của chính framework** hơn can thiệp thủ công vào mức của từng ký tự.

## 10. Unicode bidi controls: nhúng, override, mark và isolate

Trong văn bản thuần, Unicode định nghĩa một số ký tự điều khiển **không hiển thị** nhưng có thể ảnh hưởng đến cách đặt chữ và dấu câu:

| Nhóm | Tên | Code point | Tác dụng khái quát |
| --- | --- | --- | --- |
| Mark | LRM | `U+200E` | Đánh dấu hướng LTR cục bộ |
| Mark | RLM | `U+200F` | Đánh dấu hướng RTL cục bộ |
| Mark | ALM | `U+061C` | Dấu hướng Ả Rập cục bộ |
| Embedding | LRE | `U+202A` | Bắt đầu vùng nhúng LTR |
| Embedding | RLE | `U+202B` | Bắt đầu vùng nhúng RTL |
| Termination | PDF | `U+202C` | Đóng vùng embedding/override truyền thống |
| Override | LRO | `U+202D` | Ép hướng diễn giải LTR |
| Override | RLO | `U+202E` | Ép hướng diễn giải RTL |
| Isolate | LRI | `U+2066` | Cô lập vùng LTR |
| Isolate | RLI | `U+2067` | Cô lập vùng RTL |
| Isolate | FSI | `U+2068` | Cô lập theo ký tự mạnh đầu trong vùng |
| Termination | PDI | `U+2069` | Kết thúc vùng isolate tương ứng |

Các ký tự trên **không thay chữ được lưu** theo nghĩa biến `a` thành `b`; chúng thay đổi **cách bố trí thị giác**. Một số control có thể trở nên khó phát hiện khi copy/paste hoặc review vì chúng có độ rộng bằng 0.

### Embedding khác override như thế nào?

- **Embedding** chỉ tạo ngữ cảnh hướng cho một vùng, nhưng thuật toán vẫn xét thuộc tính hướng của các ký tự bên trong.
- **Override** ép cách diễn giải hướng, có thể làm hiển thị thứ tự ký tự trái với trực giác; chỉ sử dụng trong trường hợp rất đặc biệt.
- **Isolate** cho phép vùng chèn có hướng độc lập mà không làm ảnh hưởng qua lại đến văn bản xung quanh. Đối với nội dung chèn chưa biết ngôn ngữ, đây thường là hướng tiếp cận tốt hơn embedding truyền thống.

**Cảnh báo bảo mật:** `RLO/LRO` và những control vô hình có thể được dùng để đánh lừa người đọc về **tên tệp, chuỗi hiển thị hoặc cấu trúc mã nguồn** (bidi spoofing). Không tự chèn control override vào dữ liệu người dùng chỉ để “sửa giao diện” và không coi chuỗi nhìn thấy là chứng cứ chắc chắn về thứ tự code point được lưu.

### Isolate trong văn bản thuần

Về mặt ý nghĩa của Unicode UAX #9:

~~~text
FSI + văn bản có hướng không biết trước + PDI
~~~

có tác dụng yêu cầu cô lập một phần văn bản và suy hướng từ ký tự mạnh đầu trong phần đó. Trong Java có thể viết các ký tự điều khiển bằng Unicode escape:

~~~java
String isolated = "\u2068" + userText + "\u2069";
~~~

Đây là **mảnh mã trong method**; `userText` là biến `String` được cung cấp từ trước. Khi dùng thực tế, cần hiểu thành phần hiển thị đích **có hỗ trợ đúng các isolate controls** hay không. Đặc biệt, không tự khẳng định mọi phiên bản `java.text.Bidi`, mọi terminal hoặc mọi widget đều thực hiện đầy đủ cùng một phiên bản Unicode UBA.

Với HTML, dùng markup hướng chuyên dụng thường dễ bảo trì hơn việc lưu các ký tự control vào bản dịch hay tên người dùng.

## 11. HTML/Web UI: đặt hướng theo container và cô lập phần chèn

Nếu dữ liệu được Java cung cấp cho một trang HTML, trình duyệt có cơ chế riêng để quản lý hướng:

~~~html
<section dir="rtl">
  <p>نص عربي: <bdi dir="auto">Order ABC-123</bdi></p>
</section>
~~~

Đây là **mẫu HTML** minh họa, không phải Java code. Phần tử `<bdi>` là cách cô lập văn bản có hướng chưa biết trước; `dir="auto"` cho phép trình duyệt suy hướng của nội dung. `dir="rtl"` xác định hướng của container.

Trong UI thực tế:

1. Xác định hướng **của đoạn/khối** từ ngôn ngữ hoặc loại trường.
2. Cô lập **các giá trị được chèn** (tên người, tiêu đề, mã sản phẩm) khi chúng có thể mang hướng khác container.
3. Với giá trị có hướng cố định như mã kỹ thuật LTR, chỉ rõ `dir="ltr"` ở thành phần thích hợp.
4. Luôn **HTML-escape** dữ liệu không đáng tin trước khi đưa vào markup; `bdi` không thay thế cơ chế chống HTML injection/XSS.
5. Kiểm thử cả ký hiệu ở ranh giới: dấu ngoặc, hai chấm, dấu phẩy, tiền tố, hậu tố, phần mở rộng tên file.

**Không “sửa hướng” bằng cách đảo String trong Java trước khi truyền HTML.** Khi dữ liệu đã đảo, trình duyệt có thể chạy bidi **một lần nữa**, gây kết quả khó kiểm soát.

Đối với Swing/Java2D, sử dụng khả năng hướng văn bản của component và `TextLayout`; đối với JavaFX hoặc một framework UI khác, tham khảo thuộc tính direction/orientation của chính framework.

## 12. Renderer, shaping và font: vì sao java.text.Bidi chưa đủ?

Một renderer thực sự phải kết hợp:

- **Bidi reordering**: xác định trình tự hiển thị các run.
- **Shaping**: chọn glyph và dạng nối phù hợp, đặc biệt với chữ Ả Rập.
- **Font fallback**: nếu font thiếu glyph, renderer có thể cần chọn font khác.
- **Combining marks**: gắn dấu vào chữ cơ sở ở vị trí hợp lý.
- **Line breaking**: ngắt dòng theo chiều rộng và quy tắc ngôn ngữ.
- **Cursor/selection**: ánh xạ giữa vị trí logic trong `String` và vị trí thị giác trên màn hình.
- **Mirroring**: hiển thị dấu ngoặc/ký hiệu có hành vi mirror theo ngữ cảnh bidi khi cần.

Vì vậy một hàm tự xử lý `getRunLevel` rồi ghép `substring` theo thứ tự mới **không đủ** để thay thế hệ thống layout đa ngôn ngữ.

### TextLayout trong Java2D

Java có `java.awt.font.TextLayout` để xử lý bố cục văn bản có font và ngữ cảnh render. Có thể khởi tạo một text layout như sau:

~~~java
Font font = new Font("Serif", Font.PLAIN, 20);
FontRenderContext frc = new FontRenderContext(null, true, true);
TextLayout layout = new TextLayout(text, font, frc);
~~~

Đây là **mảnh mã trong method**, cần import `java.awt.Font`, `java.awt.font.FontRenderContext`, `java.awt.font.TextLayout`; biến `text` là `String` có sẵn. Để thực sự vẽ, cần `Graphics2D`, mặt vẽ và font phù hợp. Đoạn trên minh họa cách dùng API, **không phải renderer hoàn chỉnh**.

Đặc biệt, nếu giao diện dùng HTML/browser, không cần tự tạo `TextLayout` ở backend Java chỉ để trình duyệt vẽ chữ: hãy trả **chuỗi logic** cùng metadata hướng thích hợp.

## 13. Quan sát ký tự hướng vô hình khi debug

Một chuỗi có thể chứa `RLO`, `LRE`, `FSI` hoặc `PDI` mà log thông thường không nhìn thấy. Nếu giao diện hiển thị một tên file “đảo phần mở rộng” hoặc dấu câu nhảy vị trí, hãy kiểm tra code point thực tế thay vì đoán từ ảnh màn hình.

### Ví dụ Java 17+ đầy đủ: phát hiện bidi control cụ thể

Tạo `BidiControlAuditDemo.java`:

~~~java
import java.util.Set;

public class BidiControlAuditDemo {
    private static final Set<Integer> BIDI_CONTROLS = Set.of(
            0x061C, 0x200E, 0x200F,
            0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2066, 0x2067, 0x2068, 0x2069
    );

    public static void main(String[] args) {
        String input = "report\u202Etxt\u202C";

        System.out.println("Code units: " + input.length());
        input.codePoints()
                .filter(BIDI_CONTROLS::contains)
                .forEach(cp ->
                        System.out.printf("Bidi control: U+%04X%n", cp)
                );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BidiControlAuditDemo.java
java BidiControlAuditDemo
~~~

Đầu ra:

~~~text
Code units: 11
Bidi control: U+202E
Bidi control: U+202C
~~~

Tại sao `11`? `report` có 6 ký tự, `RLO` 1, `txt` 3, `PDF` 1: tổng 11 UTF-16 code unit. Hai ký tự control vẫn **nằm trong chuỗi**, dù thường không có glyph hiển thị.

**Đây là ví dụ auditing**, không phải công thức “xóa tất cả control”. Một số hệ thống thực sự cần các ký tự định hướng hợp lệ; một số giao thức lại cấm chúng. Cần áp dụng quy tắc theo loại dữ liệu:

- Mã/ID/tên file kỹ thuật: có thể cấm hoặc cảnh báo một tập control theo schema.
- Nội dung văn bản tự nhiên nhiều ngôn ngữ: có thể cần giữ control hợp lệ, nhưng nên dùng metadata/markup nếu có.
- Log và màn hình review bảo mật: hiển thị/escape các control để người kiểm tra nhận ra thứ tự logic.
- Nếu xóa hoặc biến đổi, phải hiểu tác động lên khả năng đọc, truy vết và định danh.

## 14. Tình huống thực tế: câu UI chèn tên, số và URL

Giả sử ứng dụng tạo thông báo trong một container RTL:

~~~text
[Câu Ả Rập] + [tên tài khoản tiếng Anh] + [số đơn hàng] + [dấu câu]
~~~

Nếu chỉ nối chuỗi:

~~~java
String message = prefix + username + " (" + orderId + ")";
~~~

đây là **mảnh mã trong method** có ba biến `String`. Nội dung theo thứ tự logic vẫn có thể đúng, nhưng trên màn hình có thể gặp hiện tượng **dấu ngoặc, dấu hai chấm hoặc ký hiệu** nằm ở vị trí bất ngờ khi phần chèn có hướng khác.

Cách thiết kế tốt hơn:

1. **Giữ nguyên từng biến** (username, orderId) trong model.
2. **Dùng bản dịch nguyên câu** hoặc mẫu thông điệp phù hợp locale, không cắt ghép nhiều mảnh ngữ pháp.
3. **Cung cấp hướng của container/paragraph** theo ngôn ngữ hiển thị.
4. **Cô lập phần chèn** khi UI framework hỗ trợ, đặc biệt các chuỗi chưa biết hướng.
5. **Kiểm thử các dấu trung tính** (ngoặc, dấu hai chấm, dấu gạch, dấu phẩy) và chuỗi chỉ gồm số.
6. **Không dùng đảo chuỗi** để bù lỗi hiển thị.

### Số, tiền và đường dẫn

Cụm chữ số thường có hành vi LTR ngay trong một đoạn RTL. Không viết code đảo chữ số `123` thành `321`. Với tiền, ví dụ `123.45 USD` hoặc số theo Arabic-Indic digits, hãy tách hai câu hỏi: **định dạng số theo locale** và **bố trí hướng theo bidi**. Thay đổi chữ số theo locale bằng `NumberFormat` không tự định nghĩa toàn bộ thứ tự visual của câu.

URL, mã sản phẩm và email thường cần đọc theo cấu trúc LTR. Nếu đặt trong câu RTL, nên cho chúng một vùng hiển thị được cô lập theo hướng phù hợp, không thay đổi nội dung như `user@example.com` hay mã `AB-123`.

## 15. Không đồng nhất hướng chữ với ngôn ngữ, script và locale

Một `Locale` như `ar-EG` hoặc `he-IL` có thể gợi ý ngôn ngữ/region thường dùng chữ RTL, nhưng **không** thay thế việc phân tích chính chuỗi. Một thông điệp tiếng Ả Rập có thể chứa hàng loạt từ Latin và số; một ứng dụng tiếng Anh có thể trích dẫn văn bản Hebrew.

Ba thông tin khác nhau:

- **Locale**: ngôn ngữ/vùng và các quy ước nội dung.
- **Script**: hệ chữ viết, ví dụ Latin, Arabic, Hebrew.
- **Text direction**: hướng trình bày của paragraph/run theo quy tắc bidi.

Không suy “mọi chuỗi trong locale tiếng Ả Rập đều có hướng RTL” rồi tự đảo toàn bộ nội dung. Đúng hơn là xác định **paragraph direction** cho UI và để thuật toán bidi giải quyết hướng từng run.

Nếu đang nhận nội dung từ người dùng trong chat, hướng mỗi message có thể khác nhau; metadata ngôn ngữ người dùng không đủ để quyết định hướng của mọi câu do người dùng viết.

## 16. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đảo toàn bộ `String` khi có Hebrew/Arabic | Số, dấu kết hợp, emoji, URL, thứ tự logic bị hỏng | Giữ chuỗi logic; dùng renderer bidi |
| Nghĩ RTL nghĩa là mọi ký tự bên trong đều RTL | Số và phần Latin bị xử lý sai | Để UBA phân giải run/level |
| Xem `getRunCount` là số từ hoặc số ngôn ngữ | Hiểu sai: một cụm số có thể tạo run riêng | Run là khoảng cùng embedding level |
| Đọc run theo thứ tự trả về như thứ tự visual | Hiển thị sai vì run được đánh chỉ số theo logic | Dùng layout/reorder theo line |
| Nghĩ level 2 nghĩa là ký tự “cấp độ 2 quan trọng” | Hiểu sai embedding | Level chẵn/lẻ biểu thị hướng; số còn biểu thị bối cảnh nhúng |
| Gán hướng paragraph theo ký tự cuối | Dấu câu/phần chèn không ổn định | Xác định hướng nền tường minh hoặc first-strong đúng yêu cầu |
| Tách dòng sau khi đã đảo toàn chuỗi | Các đoạn cuối dòng sai thứ tự | Layout từng dòng theo UBA |
| Dùng `Bidi` như công cụ vẽ chữ Ả Rập | Thiếu shaping/glyph/line breaking | Dùng `TextLayout` hoặc UI renderer phù hợp |
| Dùng control `RLO` để “sửa” mọi dấu ngoặc | Có thể tạo text spoofing, khó debug | Dùng metadata hướng/isolate/markup |
| Trộn `TextAttribute.BIDI_EMBEDDING` với control embedding tùy ý | Quy tắc ưu tiên khó dự đoán | Chọn một chiến lược dựa trên API |
| Tưởng `String.length()` là số glyph nhìn thấy | Sai với surrogate pair/combining mark | Phân biệt UTF-16, code point và grapheme |
| Không kiểm tra control vô hình trong input nhạy cảm | Rủi ro nhìn sai tên file, source code hoặc ID | Audit và áp dụng identifier profile |
| Coi locale là lệnh đảo chuỗi | Dẫn đến sai dữ liệu | Locale, script, direction là ba lớp khác nhau |
| Dùng HTML string mà quên escape dữ liệu | XSS, không liên quan trực tiếp bidi | Escape và dùng markup hướng đúng chuẩn |

## 17. Quy trình kiểm thử một tính năng hỗ trợ bidi

Một checklist hữu ích cho GUI/API có văn bản đa ngôn ngữ:

1. Kiểm thử paragraph nền **LTR** và **RTL** với cùng các phần chèn.
2. Dùng một câu Latin xen Hebrew, một câu Arabic xen Latin và một câu chỉ số/dấu câu.
3. Kiểm tra các **mức run** với `Bidi.getRunLevel` và biết ranh giới `getRunStart/getRunLimit`.
4. Chạy `createLineBidi` trong trường hợp có ngắt dòng thực tế.
5. Kiểm thử vị trí **ngoặc, dấu hai chấm, dấu gạch**, số và ký hiệu tiền.
6. Kiểm thử **URL, email, mã sản phẩm** nằm trong câu RTL.
7. Kiểm thử ký tự combining mark, emoji, ZWJ và nội dung ngoài BMP để tránh cắt sai UTF-16.
8. Thử tên người dùng có hướng khác container và sử dụng isolate phù hợp.
9. Kiểm tra khi copy/paste: thứ tự logic sau khi sao chép có giữ đúng dữ liệu không?
10. Kiểm tra vị trí con trỏ, selection và thao tác xóa trên widget biên tập.
11. Xem xét **bidi controls vô hình** và chính sách an toàn cho tên file, code, log.
12. Kiểm thử trên **renderer thực tế** (Swing/JavaFX/browser/mobile), không chỉ đọc `Bidi` trong console.

### Bài tập

1. Tại sao `"abc \u05D0\u05D1\u05D2 123 xyz"` trong `BidiRunsDemo` có thể sinh ra các run mức 0, 1 và 2 dù chỉ chứa chữ Latin, Hebrew và số?
2. So sánh `DIRECTION_LEFT_TO_RIGHT` và `DIRECTION_RIGHT_TO_LEFT` trên cùng chuỗi. Vì sao base level và số run có thể khác?
3. Dùng `getRunStart`, `getRunLimit` và `getRunLevel` để in bảng run. Tại sao không được xem đó là thứ tự visual?
4. Giải thích ý nghĩa của mức chẵn và lẻ. Mức `3` có nhất thiết là một ngôn ngữ RTL khác mức `1` không?
5. Với `reorderVisually` và levels `{0,1,2}`, giải thích tại sao ví dụ cho `[A, C, B]` nhưng không giúp vẽ chữ Ả Rập hoàn chỉnh.
6. Tạo `AttributedString` với `RUN_DIRECTION_RTL`. Vì sao khác với việc gắn `BIDI_EMBEDDING` vào một đoạn nhỏ?
7. Phân biệt `RLE...PDF` với `RLI...PDI`. Trong giao diện web chèn tên người dùng chưa biết hướng, vì sao `bdi` là lựa chọn phù hợp?
8. Tìm những bidi controls trong một tên file bằng `codePoints()`, rồi đề xuất chính sách validation cho tên file và nội dung bình luận riêng.
9. Thiết kế UI hiển thị câu Arabic chứa `user@example.com`. Chỉ ra các bước xử lý dữ liệu, đánh dấu hướng và rendering.
10. Giải thích tại sao cần kiểm thử dấu ngoặc và số **sau khi layout trên từng dòng**, không chỉ kiểm tra `String.equals`.

**Ghi nhớ:** văn bản hỗn hợp LTR/RTL được lưu theo **thứ tự logic** nhưng có thể hiển thị theo **thứ tự thị giác** do Unicode Bidirectional Algorithm quyết định. `java.text.Bidi` phân tích hướng nền, các run và mức nhúng; **mức chẵn LTR, mức lẻ RTL**, còn mức lớn hơn phản ánh ngữ cảnh lồng. `TextAttribute`/`TextLayout` và framework UI đảm nhận các phần hỗ trợ hiển thị. Cần ưu tiên metadata hướng và **isolation** cho phần chèn thay vì đảo chuỗi hay dùng override vô hình; luôn kiểm tra security và Unicode khi xử lý dữ liệu người dùng.

### Tài liệu tham khảo

- [Java SE 17 — Bidi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html) — constructors, mức nhúng, run, `createLineBidi` và `reorderVisually`.
- [Java SE 17 — TextAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextAttribute.html) — `RUN_DIRECTION`, `BIDI_EMBEDDING` và quy tắc ưu tiên.
- [Java SE 17 — TextLayout](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextLayout.html) — layout văn bản phức tạp.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — `getDirectionality` và code point.
- [Unicode Standard Annex #9 — Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/) — chuẩn về paragraph, embedding, override, isolate và thứ tự visual.
- [W3C — Strings on the Web: Language and Direction Metadata](https://www.w3.org/TR/string-meta/) — metadata hướng cho văn bản và ứng dụng web.