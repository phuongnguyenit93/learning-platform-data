# Phông chữ, glyph và vì sao mã hóa đúng chưa bảo đảm hiển thị đúng

## 1. Vấn đề: Unicode đúng nhưng màn hình vẫn hiển thị ô vuông

Một ứng dụng Java có thể đọc tệp UTF-8 chính xác, giữ nguyên chuỗi `String`, không làm hỏng dấu tiếng Việt và vẫn hiển thị các ký hiệu như `□`, `�`, những ô vuông thường được gọi là *tofu*, dấu bị lệch, ký tự Ả Rập không nối đúng hoặc emoji bị tách thành nhiều biểu tượng.

Có hai câu hỏi khác nhau:

1. **Dữ liệu đã được giải mã thành đúng các ký tự Unicode chưa?** Đây là vấn đề encoding/decoding, code point và việc truyền/lưu chuỗi.
2. **Hệ thống hiển thị có thể biến các ký tự ấy thành hình vẽ đúng không?** Đây là vấn đề phông chữ, glyph, ánh xạ glyph, định hình chữ (*text shaping*), thứ tự hai chiều (*bidirectional layout*), rasterization và môi trường render.

Đọc đúng byte UTF-8 **chỉ hoàn thành phần đầu của pipeline**. Không có gì trong `StandardCharsets.UTF_8` bảo đảm rằng máy người dùng có font chứa glyph cho từng chữ, font có khả năng ghép chữ Ả Rập, hoặc bộ render hỗ trợ emoji nhiều code point.

Một pipeline khái quát:

```text
Byte trong tệp/network
      │ decode bằng charset đúng
      ▼
Java String (các đơn vị mã UTF-16)
      │ hiểu code point, normalization, ký tự kết hợp
      ▼
Phân đoạn văn bản + hướng chữ + script/language runs
      │ chọn font, font fallback, shaping
      ▼
Glyph ID + vị trí glyph + advance/metrics
      │ rasterize / vẽ theo DPI, màu, anti-alias
      ▼
Ký tự người dùng nhìn thấy trên màn hình/PDF/ảnh
```

Từng tầng có thể sinh lỗi khác nhau. Nếu dữ liệu Unicode đã đúng mà font thiếu glyph, **đổi UTF-8 sang một encoding khác không phải cách sửa phù hợp**. Nếu font có đủ ký tự nhưng không xử lý shaping/hướng văn bản, việc chọn một charset khác cũng không giúp chữ hiển thị đúng.

## 2. Phân biệt code point, UTF-16, grapheme cluster và glyph

Bốn khái niệm này dễ bị nhầm khi xử lý localization trong Java:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unicode code point** | Đơn vị mã Unicode, ký hiệu thường viết `U+XXXX` | `U+1F600` là 😀 |
| **UTF-16 code unit** | Đơn vị `char` 16 bit trong Java `String` | 😀 chiếm **hai** code unit (surrogate pair) |
| **Grapheme cluster** | Đơn vị ký tự người dùng thường nhận thức; có thể gồm nhiều code point | `e` + dấu sắc kết hợp thường được nhìn như một chữ `é` |
| **Glyph** | Hình dạng ký tự thực tế được font/render engine chọn để vẽ | Một ligature có thể là một glyph cho nhiều code point; một code point có thể có các hình glyph tùy ngữ cảnh |

**Một code point không nhất thiết bằng một glyph**; cũng không phải một grapheme luôn là một code point. Một số ví dụ quan trọng:

- Chữ `é` có thể là `U+00E9` (dựng sẵn), hoặc `U+0065 U+0301` (chữ `e` và dấu sắc kết hợp). Hai chuỗi có thể hiển thị gần như giống nhau, nhưng khác độ dài UTF-16 và khác `String.equals` trước khi chuẩn hóa.
- Emoji 😀 là một code point ngoài BMP, nhưng `String.length()` trả **2** trong Java.
- Emoji gia đình, lá cờ và emoji có biến thể có thể bao gồm nhiều code point, dấu chọn biến thể `U+FE0F`, ký tự nối zero-width `U+200D` hoặc cặp regional indicator. Việc hiện thành một biểu tượng duy nhất phụ thuộc font/renderer.
- Trong chữ Ả Rập, hình vẽ của một chữ có thể đổi theo vị trí và các chữ lân cận; các chuỗi ký tự có thể được nối/định hình thành những glyph khác nhau.
- Với các hệ chữ có dấu kết hợp, vị trí dấu được tính từ glyph metrics và shaping; không đủ chỉ kiểm tra font có thể “hiện từng code point”.

**Không dùng `String.length()` để kết luận số chữ người dùng nhìn thấy.** Java cung cấp `String.codePointCount(...)` để đếm code point, nhưng ngay cả phép đếm này vẫn không tương đương số grapheme cluster hoặc số glyph được render.

## 3. Encoding và font giải quyết hai vấn đề khác nhau

### 3.1. UTF-8/UTF-16 là cách mã hóa dữ liệu

UTF-8 mô tả cách biểu diễn Unicode thành bytes; Java `String` sử dụng chuỗi các code unit UTF-16. Khi đọc tài nguyên từ tệp hoặc network, cần biết **charset thực sự của nguồn**:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Đoạn trên cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`, với biến `path` được cung cấp; không phải chương trình hoàn chỉnh.

Nếu decode sai, dữ liệu trong `String` đã hỏng và có thể thấy dạng “mojibake” như `Tiáº¿ng Viá»‡t`. Khi đó phải kiểm tra bytes và charset của luồng vào, không vội thay font.

Nếu decode đúng, ta có thể kiểm tra code point, thực hiện `String.equals`, `Normalizer` và các thao tác khác trong Java. Nhưng Unicode **không gắn sẵn hình vẽ cuối cùng** của mọi ký tự với một font cụ thể.

### 3.2. Font cung cấp các glyph và chỉ dẫn hiển thị

Một font có thể chứa:

- Bảng ánh xạ mã ký tự sang glyph (thường thông qua cơ chế kiểu `cmap` của OpenType/TrueType).
- Hình dạng glyph dưới dạng outline hoặc dữ liệu bitmap/màu.
- Số đo (*metrics*) như ascent, descent, advance, kerning.
- Bảng tính năng shaping/định vị (ví dụ các cơ chế OpenType như GSUB/GPOS), có thể cần cho ligature, dấu kết hợp và chữ phức tạp.

Nếu font không có glyph thích hợp, hệ thống có thể:

1. Thử một font thay thế (*font fallback*) có hỗ trợ ký tự.
2. Dùng glyph thay thế `missing glyph` — thường trông như ô vuông.
3. Bỏ qua ký tự, hiển thị sai hoặc dùng glyph từ font khác có metrics không khớp.

**Thiếu glyph không đồng nghĩa bytes UTF-8 bị lỗi.** Hãy dùng công cụ chẩn đoán code point và font coverage để biết lỗi nằm ở tầng nào.

### 3.3. Glyph ID không phải Unicode code point

Một renderer thường tạo ra các **glyph ID** nội bộ của font sau bước ánh xạ/shaping. Glyph ID chỉ có ý nghĩa trong phạm vi font và bộ định hình tương ứng; không được lưu nó thay cho văn bản Unicode hoặc gửi như định danh ký tự qua giao thức.

Ví dụ tính năng ligature có thể biến chuỗi ba ký tự `f`, `f`, `i` thành glyph `ﬃ` khi render. Chuỗi gốc vẫn là `ffi` nếu nguồn nhập như vậy. Ngược lại, một ký tự Unicode có thể dùng nhiều hình glyph ngữ cảnh trong các hệ chữ nối. Vì vậy **số glyph không cố định bằng số code point**.

## 4. Vì sao font fallback vẫn có thể chưa đủ?

Một ứng dụng có thể chọn phông `SansSerif` hoặc `Dialog`, hoặc font vật lý như `Arial`, `Noto Sans`, `Serif`. Cần phân biệt:

- **Font vật lý:** font cụ thể được cài đặt/đưa theo ứng dụng. Khả năng chứa glyph phụ thuộc phiên bản và file font.
- **Font logic Java:** tên logic như `Dialog`, `DialogInput`, `SansSerif`, `Serif`, `Monospaced`; Java có thể ánh xạ chúng tới một hay nhiều font vật lý theo hệ thống.
- **Font fallback:** cơ chế chọn font khác khi font ưu tiên không hỗ trợ ký tự hoặc cụm ký tự cần render. Thứ tự và chất lượng fallback phụ thuộc OS, runtime, ứng dụng, font đã cài, hệ thống render và script.

Nếu một cụm chữ gồm ký tự cơ sở và dấu kết hợp lấy từ **hai font khác nhau**, dấu có thể lệch vị trí. Nếu emoji nhiều thành phần bị chia giữa các font hoặc engine không xử lý chuỗi ZWJ, kết quả có thể là nhiều hình riêng thay vì một emoji. Font fallback giúp tăng độ phủ, nhưng **không bảo đảm shaping, layout và kiểu emoji đúng**.

Thêm một font có đủ glyph cũng chưa đủ để bảo đảm:

- Hỗ trợ đúng các tính năng OpenType của script.
- Ghép dấu kết hợp có vị trí hợp lý.
- Chạy đúng thuật toán hai chiều khi trộn RTL và LTR.
- Chọn dạng emoji màu hoặc đơn sắc theo ý đồ.
- Có cùng độ cao dòng và chiều rộng trên desktop, mobile, máy chủ hay khi export PDF.

Vì thế, kiểm thử giao diện bằng **mắt người** và ảnh chụp thực tế theo locale vẫn rất quan trọng.

## 5. Chương trình Java 17+: kiểm tra đúng dữ liệu Unicode trước khi đổ lỗi cho font

Ví dụ này dùng `String`, `Normalizer` và `codePointCount` để xác nhận các đặc tính có thể kiểm chứng **không phụ thuộc font cài trên máy**.

Tạo tệp **`UnicodeTextInspectionDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;

public class UnicodeTextInspectionDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println("precomposedLength=" +
                precomposed.length());
        System.out.println("decomposedLength=" +
                decomposed.length());
        System.out.println("rawEqual=" +
                precomposed.equals(decomposed));

        String normalizedA = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String normalizedB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("nfcEqual=" +
                normalizedA.equals(normalizedB));
        System.out.println("emojiUtf16Length=" +
                emoji.length());
        System.out.println("emojiCodePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("emojiFirstCodePoint=U+" +
                Integer.toHexString(
                        emoji.codePointAt(0)).toUpperCase(Locale.ROOT));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 UnicodeTextInspectionDemo.java
java -cp . UnicodeTextInspectionDemo
```

Đầu ra **xác định**, không phụ thuộc font và GUI:

```text
precomposedLength=1
decomposedLength=2
rawEqual=false
nfcEqual=true
emojiUtf16Length=2
emojiCodePoints=1
emojiFirstCodePoint=U+1F600
```

**Diễn giải:** hai cách biểu diễn chữ `é` khác nhau theo chuỗi mã Java nhưng giống nhau sau NFC; emoji có một Unicode code point mà chiếm hai đơn vị UTF-16. Không có dòng nào trong ví dụ xác nhận **emoji có hiển thị được trên màn hình** hay không — đó là một kiểm tra khác.

Khi log để debug, in code point bằng `String.codePoints()` có thể tốt hơn chỉ nhìn nội dung render trong terminal. Trên console, một font thiếu glyph vẫn có thể không hiển thị chữ, dù code point trong Java là đúng.

## 6. `Font.canDisplay` và `canDisplayUpTo`: kiểm tra phạm vi glyph

Java2D/AWT cung cấp `java.awt.Font` để làm việc với font. Các phương thức liên quan:

```java
boolean Font.canDisplay(int codePoint)
int Font.canDisplayUpTo(String text)
```

- `canDisplay(codePoint)` hỏi font có thể cung cấp glyph cho **code point** đó hay không.
- `canDisplayUpTo(text)` trả **`-1`** nếu font báo có thể hiển thị mọi ký tự trong chuỗi theo phép kiểm tra này; nếu không, trả **chỉ số UTF-16** của ký tự đầu tiên không hiển thị được.
- Kết quả phụ thuộc font được chọn và môi trường runtime.
- **Phép kiểm tra coverage không chứng minh text shaping/mark placement/ZWJ sequence/bi-directional ordering sẽ đúng.**

Tạo tệp **`FontCoverageDemo.java`**:

```java
import java.awt.Font;
import java.util.Locale;

public class FontCoverageDemo {
    private static void inspect(Font font, String label, String text) {
        int firstMissing = font.canDisplayUpTo(text);

        if (firstMissing < 0) {
            System.out.println(label + ": all code points supported"
                    + " according to Font");
        } else {
            int codePoint = text.codePointAt(firstMissing);
            System.out.println(label + ": first missing at UTF-16 index "
                    + firstMissing + ", U+"
                    + Integer.toHexString(codePoint)
                            .toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        Font font = new Font("Dialog", Font.PLAIN, 20);

        inspect(font, "Vietnamese", "Tiếng Việt");
        inspect(font, "Arabic", "\u0645\u0631\u062D\u0628\u0627");
        inspect(font, "Emoji", "\uD83D\uDE00");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FontCoverageDemo.java
java -cp . FontCoverageDemo
```

**Đầu ra không được cố định trước:** máy A có thể báo `all code points supported` ở một dòng, trong khi máy B có thể báo `first missing at UTF-16 index ...`. Sự khác biệt là **kết quả đúng theo môi trường font**, không phải lỗi của ví dụ.

Lưu ý quan trọng:

1. `Dialog` là tên **font logic**, không nhất thiết là một tệp font vật lý duy nhất.
2. `Font.canDisplayUpTo` trả **vị trí UTF-16**, không phải vị trí byte của UTF-8.
3. Một font báo hỗ trợ toàn bộ code point vẫn có thể hiển thị sai **cụm glyph** nếu renderer không có shaping/positioning phù hợp.
4. Với emoji màu, `canDisplay` chưa bảo đảm màu sắc, kiểu trình bày hoặc tổ hợp ZWJ sẽ trông như thiết kế.
5. Nếu ứng dụng gửi output sang PDF, trình duyệt hoặc dịch vụ ảnh, font và renderer thực sự của kênh xuất có thể khác với môi trường chạy chương trình kiểm tra.

### Font có tồn tại thật không?

Khởi tạo `new Font("TênFont", Font.PLAIN, 20)` không phải một phép kiểm tra chặt chẽ rằng tệp font vật lý có đúng tên đã được cài. Java có thể chọn font mặc định/fallback. Nếu cần kiểm tra môi trường, dùng `GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames()` hoặc công cụ quản lý font của hệ điều hành, rồi test trực tiếp trên runtime thực tế.

**Không tự tin chỉ nhờ tên font trong cấu hình.** Font có thể được thay thế âm thầm, đặc biệt trên server/container Linux tối giản.

## 7. Text shaping: có glyph nhưng chưa chắc sắp glyph đúng

**Shaping** là bước chuyển một chuỗi Unicode thành **chuỗi glyph và vị trí glyph** phù hợp quy tắc chữ viết. Bước này có thể quyết định:

- Glyph dạng đầu/giữa/cuối khi các chữ nối nhau.
- Ligature tạo từ nhiều code point.
- Thứ tự và vị trí dấu kết hợp.
- Kerning và điều chỉnh khoảng cách.
- Các tính năng font/ngôn ngữ cụ thể.

Ví dụ tiếng Ả Rập thường cần các glyph dạng nối, còn một số hệ chữ Nam Á có các tổ hợp phụ âm và dấu nguyên âm đặc thù. Một renderer vẽ **mỗi `char` như một hình độc lập** có thể làm vỡ các quy tắc ấy.

Các cách tiếp cận cần tránh:

```java
// PHẢN DIỆN — không dùng để tự vẽ câu đa ngôn ngữ:
for (int i = 0; i < text.length(); i++) {
    drawOneChar(text.charAt(i));
}
```

Đây chỉ là **mã giả minh họa**; `drawOneChar` không phải API Java chuẩn. Vòng lặp theo `char` còn có thể chia đôi surrogate pair của emoji. Quan trọng hơn, vẽ từng ký tự riêng thường làm mất cơ hội shaping và xử lý cả cụm.

Với Java desktop, nên ưu tiên **text component/layout engine** phù hợp; khi cần kiểm soát vị trí trên Java2D, có thể dùng `java.awt.font.TextLayout` và `Graphics2D`. `Graphics2D.drawString` cũng có xử lý văn bản của Java2D, nhưng khi xây renderer tùy chỉnh hãy tránh thuật toán dựa trên việc xếp từng ký tự một cách thủ công. Đặc biệt nên thử các chuỗi RTL và phức tạp trên chính JDK/OS được triển khai.

### Không thể suy ra số glyph từ số code point

Một ligature có thể cần ít glyph hơn code point; dấu kết hợp có thể dùng glyph riêng được định vị trên chữ nền; một emoji nhiều code point có thể thành một glyph hoặc nhiều glyph. Vì thế việc so `GlyphVector.getNumGlyphs()` với `text.length()` chỉ là **chẩn đoán**, không phải điều kiện “render đúng nếu bằng nhau”.

## 8. Bản địa hóa và chữ hai chiều (BiDi)

Tiếng Việt/Anh chủ yếu đọc từ trái sang phải (*left-to-right*, LTR). Tiếng Ả Rập và Hebrew có chiều viết chính từ phải sang trái (*right-to-left*, RTL). Một chuỗi có thể trộn:

```text
Nội dung RTL + mã sản phẩm ABC-123 + số 2026 + dấu câu
```

Thứ tự ký tự trong `String` (*logical order*) và thứ tự hiển thị trên màn hình (*visual order*) không phải lúc nào cũng giống nhau. Unicode Bidirectional Algorithm (BiDi) xử lý cách sắp các đoạn RTL/LTR.

Các sai lầm phổ biến:

- **Đảo ngược toàn chuỗi** bằng `new StringBuilder(text).reverse()` để “hỗ trợ RTL”. Điều đó có thể phá số, emoji, dấu kết hợp, surrogate pair và thứ tự logic.
- Thấy chuỗi Arabic có đầy đủ code point rồi khẳng định đã hỗ trợ RTL. Bộ layout còn phải quyết định hướng đoạn, số, dấu câu và thứ tự trình bày.
- Chỉ đổi alignment sang RIGHT nhưng không quan tâm hướng văn bản, caret, vị trí icon, cấu trúc form, thao tác focus hay bố cục.
- Gắn các đoạn dữ liệu LTR như URL, mã ID, số điện thoại trong câu RTL mà không kiểm thử dấu câu và ranh giới hướng.

Trong Java, `java.text.Bidi` hỗ trợ phân tích hướng văn bản. Một số thành phần Swing có khả năng áp dụng `ComponentOrientation.RIGHT_TO_LEFT`, nhưng **không phải cứ đặt orientation là đủ để bản địa hóa toàn bộ UI**; vẫn cần kiểm tra các component, renderer và văn bản trộn script.

## 9. Chương trình Java 17+: kiểm tra hướng chữ mà không phụ thuộc font

Tạo **`BidiInspectionDemo.java`**:

```java
import java.text.Bidi;

public class BidiInspectionDemo {
    public static void main(String[] args) {
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        Bidi bidi = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("arabicIsRightToLeft=" +
                bidi.isRightToLeft());
        System.out.println("arabicRunCount=" +
                bidi.getRunCount());
        System.out.println("sourceUtf16Length=" +
                arabic.length());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BidiInspectionDemo.java
java -cp . BidiInspectionDemo
```

Đầu ra:

```text
arabicIsRightToLeft=true
arabicRunCount=1
sourceUtf16Length=5
```

Với chuỗi toàn chữ Ả Rập trong ví dụ, thuật toán nhận ra một run RTL. **Điều này không chứng minh có glyph đẹp hoặc chính xác trong font** — `Bidi` giúp phân tích chiều chữ, không phải công cụ kiểm tra font coverage.

Khi trộn văn bản có hướng khác nhau, số run có thể tăng và hướng nền có thể ảnh hưởng kết quả. Để kiểm tra bố cục thực tế, phải đưa các chuỗi có mã số, dấu câu, URL và Unicode isolate/embedding theo chính sách UI vào môi trường render cuối.

## 10. Ví dụ Java2D: tạo ảnh kiểm thử văn bản đa ngôn ngữ

Nếu cần kiểm tra một renderer, có thể tạo ảnh PNG bằng Java2D rồi **mở bằng trình xem ảnh**. Ví dụ không dựa vào giao diện Swing đang hiển thị và không yêu cầu cửa sổ GUI; nó dùng `BufferedImage`, `Graphics2D` và `TextLayout`.

Tạo tệp **`MultilingualPreviewDemo.java`**:

```java
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.font.TextLayout;
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;

public class MultilingualPreviewDemo {
    public static void main(String[] args) throws Exception {
        BufferedImage image = new BufferedImage(
                1000, 310, BufferedImage.TYPE_INT_RGB);

        Graphics2D graphics = image.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(
                    0, 0, image.getWidth(), image.getHeight());

            graphics.setRenderingHint(
                    RenderingHints.KEY_TEXT_ANTIALIASING,
                    RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

            Font font = new Font("Dialog", Font.PLAIN, 30);
            graphics.setColor(Color.BLACK);

            String[] samples = {
                    "Tiếng Việt: Trường, Đặng, Nguyễn",
                    "Arabic: \u0645\u0631\u062D\u0628\u0627",
                    "Emoji: \uD83D\uDE00  Café"
            };

            float baseline = 65f;

            for (String sample : samples) {
                TextLayout layout = new TextLayout(
                        sample, font,
                        graphics.getFontRenderContext());
                layout.draw(graphics, 35f, baseline);
                baseline += 80f;
            }
        } finally {
            graphics.dispose();
        }

        boolean written = ImageIO.write(
                image, "png", new File("font-preview.png"));

        if (!written) {
            throw new IllegalStateException(
                    "PNG writer is unavailable");
        }

        System.out.println("Created font-preview.png");
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac -encoding UTF-8 MultilingualPreviewDemo.java
java -cp . MultilingualPreviewDemo
```

Khi runtime có Java2D và bộ ghi PNG hoạt động, đầu ra console:

```text
Created font-preview.png
```

Chương trình tạo `font-preview.png` trong thư mục làm việc hiện tại. **Hình ảnh không có một đầu ra pixel cố định**: phụ thuộc font vật lý/fallback, JDK, OS, engine layout, anti-aliasing và dữ liệu glyph. Cần mở ảnh và quan sát từng dòng; nếu thấy ô vuông, glyph tách rời hoặc dấu lệch, phải chẩn đoán môi trường.

Ví dụ dùng `TextLayout` để đưa **toàn chuỗi** cho bộ định hình thay vì vẽ từng `char`. Nó vẫn **không bảo đảm** mọi emoji ZWJ, màu sắc, script hay font fallback đều render đúng ở mọi máy. Đặc biệt nếu triển khai server/container không cài font, cần kiểm tra môi trường và giấy phép font trước khi đóng gói.

### Chú ý khoảng cách và cắt chữ

Kể cả khi glyph đúng, văn bản có thể bị **clipping** nếu khung chứa quá hẹp, baseline/line height không đủ, hoặc UI cố định chiều cao bằng giá trị chỉ phù hợp với một font. Đây là lỗi layout, không phải lỗi encoding. Kiểm tra với chữ có dấu cao/thấp, font size lớn, zoom/accessibility settings và độ dài bản dịch khác nhau.

## 11. Hiển thị qua Swing, JavaFX, trình duyệt và PDF không hoàn toàn giống nhau

Một ứng dụng Java có thể đưa chuỗi qua nhiều hệ thống hiển thị:

| Kênh | Cần kiểm tra |
| --- | --- |
| **Swing/AWT** | Font logic/physical, font fallback, `ComponentOrientation`, `TextLayout`, rendering hints, bố cục và kích thước component |
| **JavaFX** | Font, khả năng render của text controls, shaping, biến thể font, hướng bố cục và phiên bản runtime |
| **Trình duyệt (web do Java server trả HTML)** | CSS `font-family`, font tải từ web, font fallback của browser/OS, `dir`, Unicode BiDi, line breaks |
| **Ảnh được render ở server** | Font cài trên server/container, DPI, anti-alias, version Java2D, glyph coverage |
| **PDF do thư viện Java sinh** | Font được nhúng/subset hay không, encoding ánh xạ ký tự, text extraction, shaping/RTL support của thư viện PDF |

Không nên giả định vì **`JLabel` trên Windows hiển thị đúng** nên PDF từ máy chủ Linux cũng đúng. Từng kênh có font/render engine khác nhau. Java server trả JSON có Unicode đúng không thể ép trình duyệt client dùng một font chứa đầy đủ glyph.

Với UI web, ví dụ khái niệm CSS:

```css
.message {
  font-family: "Noto Sans", "Arial Unicode MS", sans-serif;
}
```

Đây là **ví dụ danh sách ưu tiên**, không có nghĩa các font đó đã được cài hoặc cấp phép trên mọi máy; trình duyệt sẽ chọn fallback có sẵn. Trong production, cần xác định font được phép dùng và hỗ trợ những script sản phẩm cần, thay vì viết tên font rồi coi yêu cầu đã hoàn thành.

Nếu dùng web font, cần quan tâm hiệu năng tải, cache, CORS, file subsets, các dải `unicode-range` (nếu có), quyền sử dụng font, và trạng thái font chưa tải xong. Đừng coi một danh sách `font-family` là test coverage.

## 12. Font coverage, glyph shaping và direction phải được kiểm tra tách biệt

Một quy trình chẩn đoán hữu ích khi có báo lỗi “chữ bị ô vuông”:

1. **Kiểm tra nguồn dữ liệu:** bytes đến từ đâu, charset khi decode/encode là gì? Với UTF-8, kiểm tra có ký tự thay thế `U+FFFD` hoặc chuỗi mojibake hay không.
2. **In code point thực tế:** dùng `String.codePoints()` và mã `U+...`; đừng chỉ nhìn chữ trong log/console vì font log cũng có thể thiếu glyph.
3. **Kiểm tra biểu diễn Unicode:** chữ dựng sẵn hay combining marks; có ZWJ/variation selectors không? Normalization có được áp dụng đúng chính sách không?
4. **Xác định kênh render:** AWT, Swing, JavaFX, browser, server-side image, PDF hay terminal; không lấy kết quả kênh này thay cho kênh khác.
5. **Kiểm tra font được sử dụng thật:** font ưu tiên, font fallback, version, tệp font có sẵn và quyền truy cập. Đừng chỉ kiểm tra tên font trong CSS/Java.
6. **Kiểm tra hỗ trợ code point:** thử `Font.canDisplay`/`canDisplayUpTo` khi dùng Java2D; nếu thiếu glyph, chọn font phù hợp.
7. **Kiểm tra shaping:** với Arabic, Indic scripts, dấu kết hợp, ligature; thử cả từ/câu thay vì từng ký tự.
8. **Kiểm tra BiDi/layout:** với nội dung RTL và trộn mã LTR, thử dấu câu, số, liên kết, alignment và navigation.
9. **Kiểm tra line metrics và clipping:** khung chứa, line height, ascent/descent, font fallback đổi chiều cao chữ; kiểm thử bản dịch dài.
10. **So sánh môi trường:** JDK, OS, installed fonts, browser, headless/container, thiết bị di động; chụp ảnh môi trường gặp lỗi.
11. **Kiểm tra output sau xuất:** PDF/ảnh thực tế, không chỉ preview trong IDE hoặc desktop.
12. **Tự động hóa hồi quy:** dùng bộ chuỗi đại diện cho mỗi script/locale và kiểm tra visual/screenshot khi giá trị cao, nhưng không thay thế đánh giá của người biết ngôn ngữ.

Nếu code point trong Java đúng và cùng văn bản hiển thị đúng ở máy A nhưng lỗi ở máy B, đây là bằng chứng mạnh cho hướng điều tra **font/renderer/environment** hơn là thay đổi lại encoding toàn bộ hệ thống. Tuy nhiên, vẫn cần đối chiếu dữ liệu đầu vào ở cả hai môi trường trước khi kết luận.

## 13. Các lỗi đặc biệt khi hiển thị tiếng Việt

Dấu tiếng Việt là ví dụ tốt để thấy **encoding đúng không đồng nghĩa vị trí dấu đúng**:

- Một chữ có thể có nhiều dấu kết hợp và cần font hoặc renderer đặt dấu theo quy tắc tiếng Việt.
- Một số font có glyph cơ sở nhưng khả năng neo dấu (*mark positioning*) kém; hậu quả là dấu chồng sai vị trí hoặc đè vào chữ kế bên.
- Font fallback giữa ký tự cơ sở và dấu có thể làm độ cao, advance hoặc vị trí dấu không đồng nhất.
- Chữ `Đ/đ` là các code point riêng; không tự trở thành `D/d` khi normalize NFC/NFD.
- Dữ liệu từ IME hoặc copy-paste có thể ở dạng NFC/NFD khác nhau nhưng vẫn hợp lệ về ngôn ngữ. Chuẩn hóa canonical có thể làm so sánh thuận tiện hơn, nhưng không tự sửa lỗi mark positioning.
- Độ dài một chuỗi hiển thị bằng `String.length()` có thể khác số “chữ”; đừng cắt giao diện ngay tại một `char` khi văn bản có dấu kết hợp hoặc surrogate pair.

Khi chọn font cho sản phẩm tiếng Việt, đừng chỉ kiểm thử ký tự ASCII và một từ ngắn. Hãy thử các nhóm: `ă`, `â`, `ê`, `ô`, `ơ`, `ư`, `đ`, cùng các dấu thanh và cả văn bản viết hoa. Kiểm tra trên font size nhỏ/lớn, bold/italic và những chỗ có line height cố định.

**Không nên tự “bỏ dấu” để tránh lỗi font.** Việc chuyển `Tiếng Việt` thành `Tieng Viet` làm mất thông tin ngôn ngữ và thường không phải giải pháp localization chấp nhận được. Phải sửa font/renderer hoặc cách chọn font đúng cách.

## 14. Emoji, variation selector và chuỗi ZWJ

Một vấn đề rất dễ gặp ở giao diện đa nền tảng là emoji hiển thị khác nhau:

- Một số code point có dạng chữ (*text presentation*) và dạng emoji; **variation selector** có thể gợi ý kiểu hiển thị.
- Một emoji dạng người hoặc gia đình có thể gồm nhiều code point và `U+200D` (zero-width joiner).
- Cặp regional indicator có thể tạo emoji quốc kỳ nếu môi trường hỗ trợ.
- Một máy có font màu/renderer hỗ trợ glyph tổ hợp; máy khác có thể hiện hình đơn sắc, các thành phần rời hoặc ô vuông.

`Font.canDisplayUpTo` trả `-1` **không đủ** để xác nhận cả chuỗi ZWJ biến thành một emoji như mong muốn. Cần thử trực tiếp trên các nền tảng mục tiêu.

Với Java, cần đi qua code point đúng cách nếu xử lý emoji:

```java
String emoji = "\uD83D\uDE00";
int count = emoji.codePointCount(0, emoji.length());
```

Trích đoạn trên cho `count == 1`. Dùng `emoji.charAt(0)` rồi hiển thị độc lập sẽ lấy **một nửa surrogate pair**, không phải emoji hoàn chỉnh.

Không nên quyết định cắt text, di chuyển caret hoặc xóa ký tự bằng phép trừ một đơn vị UTF-16 tùy ý. Với chức năng chỉnh sửa, cần quan tâm **ranh giới grapheme cluster**, đặc biệt với emoji, dấu kết hợp và script phức tạp.

## 15. BiDi trong giao diện: không chỉ đảo chiều căn lề

Khi hỗ trợ Arabic/Hebrew, cần tách:

- **Direction của đoạn văn:** thành phần bao ngoài có chủ đích RTL hay LTR?
- **Direction của các đoạn chữ bên trong:** chữ Arabic, Latin, số, dấu câu có thể có hướng khác nhau.
- **Thứ tự logic:** `String` lưu dữ liệu theo thứ tự văn bản, không nên tự đảo phần tử để tạo hiệu ứng nhìn.
- **Layout của giao diện:** icon trước/sau nhãn, menu, breadcrumb, thanh điều hướng, caret, phím mũi tên và focus order.
- **Ngữ cảnh chèn nội dung không tin cậy:** dữ liệu tên người/đơn hàng/URL có thể cần *isolation* để không ảnh hưởng hướng của câu bao quanh.

Ví dụ, nếu một câu Arabic chứa `ABC-123`, phần mã thường nên giữ thứ tự nội tại LTR. Thao tác `reverse()` cả chuỗi có thể làm hỏng mã và dấu câu. Dùng **Unicode BiDi-capable layout** và khi thích hợp các cơ chế isolation của nền tảng hiển thị.

Trong Swing, `ComponentOrientation.RIGHT_TO_LEFT` giúp một số component/layout thích nghi, nhưng không thay thế kiểm tra rendering từng thành phần. Một số đồ họa tùy chỉnh hoặc biểu tượng có hướng vẫn phải được xử lý riêng; không phải icon nào cũng cần mirror (logo, biểu tượng play, đồng hồ... phụ thuộc ngữ nghĩa thiết kế).

## 16. Khi cần đóng gói font theo ứng dụng

Đôi khi nền tảng mục tiêu không bảo đảm có font thích hợp. Một ứng dụng desktop/server có thể đóng gói font hoặc dùng cơ chế phân phối font do sản phẩm quản lý.

Trong Java2D, `Font.createFont` có thể tải một font từ file/stream theo những định dạng hỗ trợ. Ví dụ khái niệm:

```java
// Trích đoạn: phải có tài nguyên font thực và quyền sử dụng.
try (InputStream stream =
        MyClass.class.getResourceAsStream("/fonts/app-font.ttf")) {
    if (stream == null) {
        throw new IllegalStateException("Font resource missing");
    }

    Font font = Font.createFont(Font.TRUETYPE_FONT, stream)
            .deriveFont(20f);
}
```

Đoạn trên cần import `java.awt.Font`, `java.io.InputStream` và một class `MyClass` trong dự án; không phải chương trình độc lập vì tài nguyên font được giả định tồn tại. Không đưa font vào repository hay phân phối lại nếu giấy phép không cho phép.

Trước khi chọn phương án đóng gói font:

1. Kiểm tra font có chứa các script, glyph, biến thể và tính năng shaping sản phẩm cần.
2. Kiểm tra bộ renderer và hệ điều hành thật sự sử dụng font mong muốn; thêm font vào classpath không tự bảo đảm mọi text component/PDF/browser sẽ dùng nó.
3. Xem xét license về phân phối/nhúng, kể cả PDF subset và ứng dụng thương mại.
4. Kiểm tra chiều cao dòng, kiểu bold/italic, Unicode variation selectors và khả năng fallback.
5. Nếu có nhiều bộ font cho từng script, xác định chiến lược fallback nhất quán để tránh nhảy kích thước và độ dày giữa các phần của cùng một từ.

Ở ứng dụng web, nhúng/tải web font thông qua CSS là một pipeline khác với `Font.createFont` trong Java server. Không vì Java server có font mà browser tự được cung cấp font đó.

## 17. Không nhầm lỗi mã hóa với lỗi hiển thị

| Triệu chứng | Nguyên nhân thường cần kiểm tra | Hướng sửa phù hợp |
| --- | --- | --- |
| Chuỗi thành `Tiáº¿ng Viá»‡t` | Sai charset khi decode/encode ở một tầng | Kiểm tra bytes, UTF-8 và cấu hình pipeline |
| Chuỗi có `U+FFFD` xuất hiện từ lúc decode | Bytes đầu vào sai hoặc decoder thay thế dữ liệu không giải mã được | Kiểm tra nguồn bytes, cách xử lý lỗi decode |
| Code point đúng nhưng ô vuông/tofu | Font thiếu glyph hoặc fallback không hoạt động | Chọn/cài font đúng, kiểm tra `canDisplay`, test render |
| Dấu tiếng Việt hiện lệch/chồng | Font metrics, shaping, mark positioning, fallback | Dùng font và renderer hỗ trợ tiếng Việt |
| Chữ Arabic không nối đúng | Shaping script hoặc cách render từng ký tự riêng | Dùng text layout engine phù hợp |
| Văn bản Hebrew/Arabic với mã Latin bị đảo dấu câu | BiDi direction/isolation/layout | Sửa hướng đoạn và xử lý BiDi, không đảo `String` |
| Emoji thành nhiều biểu tượng rời | Renderer/font chưa xử lý chuỗi ZWJ/variation | Kiểm tra font emoji, engine và thiết bị mục tiêu |
| Chỉ lỗi khi xuất PDF | Font embedding/subsetting hoặc engine PDF | Kiểm tra font và shaping của thư viện PDF |
| Chữ bị cắt khi đổi locale | Bản dịch dài, font metrics, kích thước container | Thiết kế layout co giãn, thử accessibility font size |
| Chỉ lỗi trên máy chủ container | Thiếu bộ font/khác JDK/OS | Kiểm tra image/deployment và font đã cài |
| `String.equals` trả khác nhưng hình chữ như nhau | Biểu diễn Unicode dựng sẵn/phân rã, hoặc homoglyph | Chọn chính sách normalization/identity phù hợp |
| Dữ liệu hiển thị được nhưng không thể tra cứu | Normalization, collation, search index khác nhau | Đồng nhất hợp đồng so sánh, không tự đổi encoding |

Các mục “nguyên nhân” trong bảng là **hướng chẩn đoán**, không phải kết luận duy nhất từ một triệu chứng. Ví dụ dấu hiện lệch còn có thể do lỗi layout hoặc CSS; phải kiểm tra môi trường cụ thể.

## 18. Kiểm thử hiển thị theo locale và môi trường

Một bộ kiểm thử localization nên có nhiều tầng:

### 18.1. Kiểm thử dữ liệu

- Decode/encode UTF-8 đúng với các chuỗi mẫu.
- Kiểm tra code point trong `String` bằng giá trị `U+...`.
- Đảm bảo không tự cắt giữa surrogate pair hoặc grapheme cluster.
- Kiểm tra normalization policy nếu ứng dụng cần so khớp canonical; không chuẩn hóa bừa những dữ liệu có ý nghĩa chính xác.

### 18.2. Kiểm thử font và shaping

- Font coverage cho từng script được hỗ trợ: tiếng Việt, Arabic, Hebrew, Hindi, Thai, Hàn/Nhật/Trung nếu sản phẩm có triển khai.
- Dấu kết hợp, ligatures, chữ nối, biến thể chữ, emoji ZWJ, ký tự ngoài BMP.
- Font size nhỏ/lớn, bold/italic, zoom, high-DPI, thay font fallback.
- Những từ và câu thực, không chỉ bảng từng ký tự riêng biệt.

### 18.3. Kiểm thử chiều chữ và bố cục

- Đoạn LTR, RTL và chuỗi trộn.
- Số, URL, mã đơn, dấu câu trong câu RTL.
- Alignment, input caret, selection, copy/paste, keyboard navigation.
- Label, button, tooltip, dialog, thông báo lỗi, nội dung dài.
- Độ dài bản dịch khác nhau, khả năng co giãn/dòng mới.

### 18.4. Kiểm thử kênh xuất và deployment

- Desktop OS chính: Windows/macOS/Linux nếu hỗ trợ.
- Headless server/container, danh sách font thực tế khi dựng ảnh.
- Browser và thiết bị di động mục tiêu nếu Java trả nội dung web.
- PDF/ảnh/print output nếu tính năng có xuất file.
- Java runtime/JDK updates, các phiên bản font và shaping engine.

### 18.5. Kiểm thử tính dễ đọc và hỗ trợ tiếp cận

- Bật tăng cỡ chữ, scale UI, chế độ tương phản cao.
- Kiểm tra vị trí dấu và độ rõ ở kích thước nhỏ.
- Đừng dùng một glyph/icon để truyền nghĩa độc nhất nếu hệ thống đọc màn hình không thể diễn giải.
- Với nội dung trộn script, thử screen reader và đọc theo thứ tự logic.
- Tham khảo phản hồi người dùng bản địa khi kiểm tra glyph, hướng chữ và dấu câu.

**Không có một assertion Java duy nhất xác nhận “hiển thị đẹp cho mọi locale”.** Kiểm thử tự động xác nhận encoding/code point; phép `canDisplay` gợi ý coverage; screenshot test và review thực tế giúp đánh giá kết quả người dùng nhìn thấy.

## 19. Câu hỏi thường gặp

**File đã lưu UTF-8, vậy tại sao vẫn có ô vuông?**

UTF-8 giải quyết mã hóa bytes. Nếu `String` đã chứa code point đúng, ô vuông thường liên quan đến font, fallback hoặc renderer. Cần phân tích từng tầng thay vì đổi charset ngẫu nhiên.

**`Font.canDisplayUpTo(text) == -1` có chứng minh mọi ký tự sẽ hiện đẹp?**

Không. Kết quả cho biết font báo hỗ trợ những code point tương ứng theo phép kiểm tra; không bảo đảm shaping, vị trí dấu, ligature, emoji màu, hướng chữ, độ rộng layout hay bộ render PDF.

**Dùng `Dialog` có phải font luôn có mọi chữ không?**

Không. Đây là font logic có thể ánh xạ tới các font vật lý khác nhau theo runtime/OS. Khả năng hiển thị thực tế phụ thuộc font đã cài và cơ chế fallback.

**`Normalizer.normalize(text, NFC)` có sửa được font thiếu glyph không?**

Không. NFC đưa các biểu diễn canonical-equivalent về một dạng nhất quán. Nó có thể thay code point composition nhưng không tự cài font hoặc cung cấp glyph còn thiếu.

**Vì sao chữ Arabic vẫn không đọc đúng khi code point đúng?**

Cần text shaping và BiDi layout. Vẽ từng code point độc lập hoặc đảo chuỗi thủ công có thể phá cách nối chữ/hướng đoạn.

**Một emoji có phải một ký tự Java `char` không?**

Không nhất thiết. Emoji 😀 là một code point nhưng chiếm hai code unit UTF-16; các emoji tổ hợp có thể gồm nhiều code point và nhiều code unit.

**Có cần gộp mọi font thành một font chứa tất cả Unicode không?**

Thường không thực tế. Hệ thống dùng fallback/chia font theo script; quan trọng là chọn font, shaping engine và chiến lược thay thế hoạt động nhất quán, kiểm tra được trên nền tảng mục tiêu.

**Có nên xóa ký tự lạ hoặc tự chuyển chúng sang ASCII?**

Không tự động. Việc đó có thể làm mất dữ liệu/ngữ nghĩa, nhất là tên riêng và chữ không Latin. Nếu trường nghiệp vụ chỉ cho phép một tập ký tự, cần quy định validation rõ ràng và thông báo phù hợp; không lấy lỗi render làm lý do thay đổi nội dung người dùng.

## 20. Ghi nhớ

- **Mã hóa đúng chưa bảo đảm hiển thị đúng.** UTF-8/UTF-16 giải quyết biểu diễn Unicode; font và renderer giải quyết glyph, shaping, metrics, BiDi và rasterization.
- **Code point, UTF-16 code unit, grapheme cluster và glyph không phải một.** Tránh xử lý từng `char` như từng “ký tự người dùng”.
- **Font coverage là cần nhưng chưa đủ.** `Font.canDisplay` và `canDisplayUpTo` hỗ trợ chẩn đoán thiếu glyph; vẫn cần kiểm thử shaping và kết quả render.
- **Font fallback không phải hợp đồng hiển thị thống nhất** giữa Windows, Linux, macOS, Java2D, browser, server và PDF. Chọn font và cấu hình theo kênh xuất thực tế.
- **Văn bản RTL không thể xử lý bằng đảo chuỗi thủ công.** Hãy dùng engine/layout hỗ trợ Unicode BiDi và kiểm thử nội dung trộn Latin, số và dấu câu.
- **Không dùng normalization để chữa mọi lỗi font** và không loại bỏ dấu/ký tự Unicode của người dùng chỉ để tránh ô vuông.
- **Kiểm thử nhiều tầng:** code point → font coverage → shaping → hướng chữ → ảnh/screenshot/PDF trên môi trường triển khai; kết hợp kiểm thử tự động với đánh giá từ người hiểu ngôn ngữ.
