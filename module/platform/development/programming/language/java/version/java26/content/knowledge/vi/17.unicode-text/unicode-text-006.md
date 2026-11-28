# Xử lý văn bản hai chiều với Bidi khi có nhu cầu

Khi một đoạn văn bản trộn chữ viết từ trái sang phải (LTR) với chữ viết từ phải sang trái (RTL), thứ tự lưu trong chuỗi không nhất thiết trùng với thứ tự nhìn thấy trên màn hình. Ví dụ, một câu tiếng Ả Rập hoặc Hebrew có thể chứa tên sản phẩm Latin, số đơn hàng, dấu ngoặc và dấu câu. Nếu tự đảo chuỗi để hiển thị, thứ tự số, dấu câu và cụm chữ có thể sai.

Java cung cấp **java.text.Bidi** để phân tích hướng hiển thị theo Unicode Bidirectional Algorithm (UBA). API này cho biết hướng cơ sở, các run và mức hướng (embedding level) để tầng trình bày bố trí nội dung. **Bidi không phải API mới của Java 26**: lớp này ổn định từ Java 1.4, thuộc module `java.base`, tiếp tục có trong JDK 26 và JDK 27. Không cần preview flag hoặc dependency ngoài.

Chỉ dùng Bidi trực tiếp khi ứng dụng tự xây dựng bộ dàn trang, trình soạn thảo, bố trí run hoặc cần thông tin hướng để đặt thành phần nội tuyến. Nếu mục tiêu chỉ là hiển thị văn bản trong Swing/Java2D, hãy ưu tiên thành phần hoặc API layout đã xử lý bidi như `TextLayout`; không tự viết lại thuật toán.

## 1. Logical order và visual order

Unicode lưu văn bản theo **logical order**: thứ tự ký tự được nhập, đọc và xử lý. Thuật toán bidi chỉ thay đổi cách sắp xếp để hiển thị, không yêu cầu thay đổi thứ tự lưu trữ.

Ví dụ một đoạn văn RTL có thể chứa:

- Chữ Ả Rập hoặc Hebrew theo hướng phải sang trái.
- Tên thương hiệu hoặc mã sản phẩm Latin theo hướng trái sang phải.
- Chữ số và dấu phân cách có quy tắc hướng riêng.
- Dấu ngoặc, dấu câu và khoảng trắng là các ký tự trung tính hoặc yếu, cần ngữ cảnh để xác định vị trí.

Vì vậy, cùng một chuỗi có thể gồm nhiều đoạn hiển thị theo các hướng khác nhau. Hướng của cả đoạn văn được gọi là **base direction**; mỗi đoạn con có hướng riêng được gọi là **directional run**.

Ví dụ khái niệm:

    Logical order (chuỗi lưu trong Java):
    "رقم الطلب AB-1234 تم الشحن"

    Visual layout:
    [các run được bố trí theo base direction và embedding level]

Không dùng visual order làm dữ liệu lưu trữ, nội dung tìm kiếm, dữ liệu gửi API hoặc đầu vào parser. Việc đổi logical order sang visual order có thể mất thông tin và không có một phép đảo ngược tổng quát an toàn. Chỉ thực hiện bố trí trực quan ở tầng hiển thị.

## 2. Unicode Bidirectional Algorithm giải quyết vấn đề gì?

**Unicode Standard Annex #9 (UAX #9)** định nghĩa thuật toán bidi. Thuật toán xem xét thuộc tính hướng của từng ký tự, xác định mức hướng và sắp xếp các ký tự trong từng dòng để hiển thị.

Có ba nhóm hướng chính:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| Strong | Có hướng chữ viết rõ ràng | Chữ Latin LTR, chữ Ả Rập/Hebrew RTL |
| Weak | Hướng phụ thuộc quy tắc và ngữ cảnh | Chữ số, dấu phân cách số |
| Neutral | Không có hướng riêng đủ mạnh | Khoảng trắng, nhiều dấu câu, dấu ngoặc |

Thuật toán không chỉ đảo toàn bộ câu RTL. Nó xác định hướng cơ sở, giải quyết các ký tự yếu/trung tính, xử lý các vùng lồng nhau và cuối cùng sắp xếp các run trong từng dòng.

Các mức hướng (embedding levels) được biểu diễn bằng số nguyên:

- Mức chẵn: hướng LTR.
- Mức lẻ: hướng RTL.
- Mức 0 thường là LTR ở đoạn có base direction LTR.
- Mức 1 thường là RTL ở đoạn có base direction RTL.
- Mức 2 là LTR được lồng bên trong vùng RTL; các mức cao hơn tiếp tục thể hiện lồng hướng.

Một directional run là vùng liên tiếp có cùng embedding level. Các run được truy xuất theo logical order; khi cần hiển thị, tầng layout sử dụng level để bố trí chúng theo visual order.

## 3. Chọn base direction đúng

Java tạo đối tượng Bidi từ một đoạn văn và một trong bốn cờ hướng:

| Cờ | Hành vi |
|---|---|
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Cố định base direction là LTR |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Cố định base direction là RTL |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Chọn theo strong directional character đầu tiên; nếu không có thì mặc định LTR |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Chọn theo strong directional character đầu tiên; nếu không có thì mặc định RTL |

Ví dụ:

    import java.text.Bidi;

    String paragraph = "رقم الطلب AB-1234 تم الشحن";

    Bidi bidi = new Bidi(
            paragraph,
            Bidi.DIRECTION_RIGHT_TO_LEFT
    );

    System.out.println("Base level: " + bidi.getBaseLevel());
    System.out.println("Base is LTR: " + bidi.baseIsLeftToRight());
    System.out.println("Mixed: " + bidi.isMixed());

Chọn cờ dựa trên ngữ cảnh giao diện:

- Nếu đoạn văn nằm trong một khung nội dung RTL đã biết, chọn `DIRECTION_RIGHT_TO_LEFT`.
- Nếu đoạn văn nằm trong một khung LTR đã biết, chọn `DIRECTION_LEFT_TO_RIGHT`.
- Nếu nội dung tự quyết định hướng và ứng dụng chấp nhận quy tắc first-strong, dùng một trong hai cờ DEFAULT.
- Nếu văn bản không có strong character, cờ DEFAULT quyết định hướng mặc định.

Không mặc định dùng first-strong cho mọi thành phần giao diện. Ví dụ, một trường mã đơn hàng bắt đầu bằng số có thể cần LTR ngay cả khi nó nằm trong trang RTL. Base direction là quyết định của thành phần trình bày và nghiệp vụ, không chỉ là phép đoán ngôn ngữ từ chuỗi.

## 4. Kiểm tra nhanh và tránh phân tích không cần thiết

Nếu chỉ cần biết đoạn văn có cần bidi analysis hay không, có thể dùng `Bidi.requiresBidi(char[], start, limit)`:

    String text = "Invoice رقم 12345";
    char[] chars = text.toCharArray();

    if (Bidi.requiresBidi(chars, 0, chars.length)) {
        Bidi bidi = new Bidi(
                text,
                Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT
        );

        System.out.println("Runs: " + bidi.getRunCount());
    } else {
        System.out.println("Đoạn văn không cần bidi analysis");
    }

Phương thức này trả về true nếu vùng ký tự cần phân tích bidi theo quy tắc của API. Nếu false, client có thể bỏ qua việc tạo Bidi và hiển thị theo LTR.

Có một giới hạn quan trọng trong hợp đồng API: ký tự thuộc vùng **Arabic Presentation Forms** được giả định là đã shaping và sắp xếp cho hiển thị, nên không làm `requiresBidi` trả về true. Không dùng phương thức này như một phép kiểm tra toàn diện rằng chuỗi có hay không có chữ Ả Rập. Với văn bản Unicode hiện đại, nên lưu các ký tự chữ cơ sở (nominal characters) và để text layout thực hiện shaping.

`requiresBidi` chỉ là một tối ưu để bỏ qua phân tích khi không cần; nó không kiểm tra tính an toàn, không xác nhận chuỗi hợp lệ và không thay thế xử lý layout.

## 5. Đọc các directional run và embedding level

Sau khi tạo Bidi, dùng `getRunCount()`, `getRunStart()`, `getRunLimit()` và `getRunLevel()` để xem các vùng hướng:

    import java.text.Bidi;

    public class InspectBidiRuns {
        public static void main(String[] args) {
            String paragraph = "رقم الطلب AB-1234 تم الشحن";

            Bidi bidi = new Bidi(
                    paragraph,
                    Bidi.DIRECTION_RIGHT_TO_LEFT
            );

            System.out.println("Base level: " + bidi.getBaseLevel());
            System.out.println("Run count: " + bidi.getRunCount());

            for (int run = 0; run < bidi.getRunCount(); run++) {
                int start = bidi.getRunStart(run);
                int limit = bidi.getRunLimit(run);
                int level = bidi.getRunLevel(run);

                String logicalRun = paragraph.substring(start, limit);
                String direction = (level & 1) == 0 ? "LTR" : "RTL";

                System.out.printf(
                        "run=%d start=%d limit=%d level=%d direction=%s text=%s%n",
                        run, start, limit, level, direction, logicalRun
                );
            }
        }
    }

Các phương thức có ý nghĩa:

- `getRunCount()`: số run trong đoạn/dòng.
- `getRunStart(run)`: offset bắt đầu của run theo logical order.
- `getRunLimit(run)`: offset ngay sau ký tự cuối của run (exclusive).
- `getRunLevel(run)`: embedding level của run.
- `getLevelAt(offset)`: embedding level tại một offset ký tự.
- `getBaseLevel()`: mức hướng cơ sở của đoạn/dòng.

Các run được trả về theo logical order, không phải thứ tự để vẽ từ trái sang phải trên màn hình. Dùng level để quyết định bố trí. Không giả định một đoạn văn luôn chỉ có hai run; chữ số, dấu ngoặc, dấu câu và các vùng lồng hướng có thể tạo ra nhiều run hơn.

### Offset của Bidi là offset UTF-16

Các chỉ số start/limit và offset mà Bidi nhận là offset theo đơn vị `char` của Java, tức UTF-16 code unit. Đây cũng là đơn vị chỉ số của `String.substring`, nên có thể dùng trực tiếp với chuỗi gốc như ví dụ trên.

Không diễn giải offset này là số Unicode code point, số grapheme cluster hoặc vị trí pixel. Một ký tự supplementary có thể chiếm hai UTF-16 code unit; một grapheme hiển thị có thể gồm nhiều code point. Không cắt chuỗi tại vị trí tùy ý nếu có thể chia đôi surrogate pair hoặc chuỗi dấu kết hợp. Với caret, selection và hit testing, dùng API text layout có hỗ trợ grapheme/caret thay vì tự tính từ Bidi level.

## 6. Sắp xếp các run theo visual order

Nếu ứng dụng có các object đại diện cho run (ví dụ đoạn chữ, inline icon, placeholder hoặc thành phần giao diện), có thể dùng `Bidi.reorderVisually(...)` để sắp xếp các object theo level:

    import java.text.Bidi;

    static Object[] visualRunOrder(String paragraph, Bidi bidi) {
        int count = bidi.getRunCount();

        byte[] levels = new byte[count];
        Object[] runs = new Object[count];

        for (int i = 0; i < count; i++) {
            int start = bidi.getRunStart(i);
            int limit = bidi.getRunLimit(i);

            levels[i] = (byte) bidi.getRunLevel(i);
            runs[i] = paragraph.substring(start, limit);
        }

        Bidi.reorderVisually(
                levels,
                0,
                runs,
                0,
                count
        );

        return runs;
    }

Phương thức này thay đổi thứ tự object trong mảng theo visual order. Nó hữu ích khi mỗi object đã đại diện cho một run đồng nhất về hướng.

**Không được hiểu reorderVisually là thao tác đảo ký tự bên trong mỗi String.** Phương thức chỉ sắp xếp các object/run. Một run RTL vẫn cần được layout và shaping theo hướng RTL để glyph hiển thị đúng. Không nối các run thành một chuỗi rồi đảo từng ký tự để tạo visual text; cách đó làm hỏng chữ Ả Rập, dấu kết hợp, ligature và thứ tự số.

Nếu ứng dụng chỉ cần vẽ văn bản, dùng `TextLayout` hoặc text component thay vì tự ghép run rồi vẽ.

## 7. Phân tích paragraph và xử lý line wrapping

Bidi được áp dụng theo từng paragraph. Kết quả sắp xếp trực quan còn phụ thuộc vào ranh giới dòng vì các quy tắc cuối dòng có thể thay đổi level của whitespace và ký tự định dạng.

Nếu đoạn văn được hiển thị trên một dòng, có thể dùng trực tiếp Bidi đã tạo cho paragraph. Nếu đoạn văn được ngắt thành nhiều dòng, dùng `createLineBidi(lineStart, lineLimit)` để tạo Bidi cho từng dòng dựa trên phân tích paragraph:

    Bidi paragraphBidi = new Bidi(
            paragraph,
            Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT
    );

    // Các offset dưới đây là ví dụ ranh giới dòng đã được layout xác định.
    int lineStart = 0;
    int lineLimit = paragraph.length();

    Bidi lineBidi = paragraphBidi.createLineBidi(
            lineStart,
            lineLimit
    );

    System.out.println("Line runs: " + lineBidi.getRunCount());

`lineStart` và `lineLimit` là offset trong paragraph; `lineLimit` là vị trí ngay sau ký tự cuối dòng. Khi paragraph thực sự có nhiều dòng, tạo một line Bidi cho từng vùng đã được line breaker xác định.

Không tự chia dòng theo số ký tự trước khi phân tích layout. Chiều rộng glyph, font, shaping và hướng run ảnh hưởng đến line break. Nếu dùng Java2D, `LineBreakMeasurer` cùng `TextLayout` có thể thực hiện ngắt dòng và bố trí bidi với đủ ngữ cảnh. Nếu tự viết renderer, cần duy trì ngữ cảnh paragraph và áp dụng line-level processing đúng theo UAX #9.

Với văn bản có nhiều paragraph, tách theo ranh giới paragraph trước khi phân tích. Không gộp các đoạn độc lập vào một Bidi object rồi giả định ký tự trong paragraph trước có thể ảnh hưởng đến base direction của paragraph sau.

## 8. Khi nào dùng TextLayout thay vì Bidi trực tiếp?

`java.text.Bidi` cung cấp metadata hướng và run. Nó không phải engine hoàn chỉnh để chọn glyph, shaping chữ phức tạp, đo advance, đặt caret hoặc vẽ nội dung.

Nếu ứng dụng hiển thị văn bản trong Java desktop, xem xét các lựa chọn:

| Nhu cầu | API phù hợp |
|---|---|
| Hiển thị một chuỗi đơn giản, có thể chứa bidi | `Graphics2D.drawString(...)` với Java2D text layout |
| Hiển thị và đo một paragraph có nhiều hướng/font | `java.awt.font.TextLayout` |
| Ngắt paragraph thành các dòng vừa chiều rộng | `LineBreakMeasurer` kết hợp `TextLayout` |
| Xây dựng editor cần caret, hit testing, selection hai chiều | `TextLayout` và các API caret/hit-test của nó |
| Cần tự bố trí run hoặc inline object theo embedding level | `java.text.Bidi` kết hợp text shaping/rendering phù hợp |
| Ứng dụng web | Dùng HTML `dir`, `<bdi>` và CSS direction/unicode-bidi ở tầng trình bày |

Ví dụ vẽ một paragraph bằng TextLayout trong một component Java2D:

    import java.awt.Font;
    import java.awt.Graphics2D;
    import java.awt.font.FontRenderContext;
    import java.awt.font.TextLayout;

    static void drawParagraph(
            Graphics2D graphics,
            String paragraph,
            float x,
            float baselineY
    ) {
        Font font = new Font("Dialog", Font.PLAIN, 18);
        FontRenderContext frc = graphics.getFontRenderContext();

        TextLayout layout = new TextLayout(
                paragraph,
                font,
                frc
        );

        layout.draw(graphics, x, baselineY);
    }

Ví dụ này giả định `paragraph` là một paragraph. TextLayout tự phân tích bidi, chọn và bố trí glyph theo khả năng font/runtime. Với đoạn dài cần wrapping, dùng `LineBreakMeasurer` thay vì tạo TextLayout từ một chuỗi nhiều paragraph.

Nếu chạy trong môi trường headless hoặc server không render giao diện, không cần thêm AWT chỉ để xử lý chuỗi hoặc lưu dữ liệu. Giữ văn bản logical order; chỉ component hiển thị mới cần bidi layout.

## 9. Directional controls: isolates, embeddings và overrides

Unicode định nghĩa các ký tự điều khiển hướng để xử lý những tình huống mà quy tắc tự động không đủ rõ ràng. Các ký tự này ảnh hưởng đến cách hiển thị, không thay đổi ý nghĩa dữ liệu, phép so sánh hoặc phân tích số.

| Nhóm | Code point | Vai trò |
|---|---|---|
| LRM / RLM / ALM | U+200E, U+200F, U+061C | Dấu hướng vô hình LTR/RTL/Arabic |
| LRE / RLE | U+202A, U+202B | Mở vùng embedding LTR/RTL |
| PDF | U+202C | Kết thúc embedding/override |
| LRO / RLO | U+202D, U+202E | Ép hướng LTR/RTL, override hướng ký tự |
| LRI / RLI / FSI | U+2066, U+2067, U+2068 | Mở isolate LTR/RTL/first-strong |
| PDI | U+2069 | Kết thúc isolate |

Với nội dung mới, Unicode khuyến khích dùng **isolates** thay vì embeddings nếu nền tảng đích hỗ trợ. Nội dung trong isolate không làm thay đổi thứ tự bên ngoài và ngược lại. Các override như RLO/LRO nên tránh trừ trường hợp rất đặc biệt vì chúng có thể khiến thứ tự hiển thị khác với nội dung logic.

Nếu cần đặt một đoạn văn bản động vào giữa paragraph RTL, có thể cô lập nội dung đó ở tầng trình bày:

    String displayText =
            "رقم الطلب "
            + "\u2068" + externalOrderCode + "\u2069"
            + " تم الشحن";

FSI (U+2068) chọn hướng của đoạn con theo strong character đầu tiên bên trong; PDI (U+2069) kết thúc isolate. Dùng cách này khi đích là plain text và bạn kiểm soát được việc tạo/duy trì các control character. Với HTML, ưu tiên markup `<bdi>` hoặc thuộc tính `dir` thay cho nhúng các control character vào nội dung.

Không thêm control characters vào dữ liệu gốc, khóa database hoặc giá trị cần so sánh nếu không có yêu cầu định dạng rõ ràng. Thêm chúng chỉ tại ranh giới hiển thị để tránh làm dữ liệu có các ký tự vô hình ngoài ý muốn.

## 10. Bảo mật: phát hiện ký tự điều khiển bidi trong dữ liệu không tin cậy

Ký tự điều khiển bidi có thể khiến tên file, log, mã nguồn hoặc thông tin hiển thị có thứ tự gây hiểu nhầm. Ví dụ, RLO có thể làm phần đuôi tên file hiển thị khác thứ tự lưu trữ. Vì vậy:

- Không tin visual order là bằng chứng cho nội dung thực trong chuỗi.
- Khi log dữ liệu không tin cậy, cân nhắc hiển thị control character dưới dạng escaped code point như `U+202E`.
- Không cho phép bidi controls trong identifier, tên file hoặc trường nghiệp vụ nếu yêu cầu sản phẩm không cần chúng.
- Không loại bỏ tất cả bidi controls một cách mù quáng khỏi văn bản tự nhiên; một số nội dung RTL hợp lệ cần isolates hoặc marks để hiển thị đúng.
- Khi review source code, kiểm tra các control characters vô hình trong chuỗi, comment và identifier.
- Phân biệt hỗ trợ RTL hợp lệ với hành vi giả mạo hiển thị; không chặn toàn bộ chữ Ả Rập/Hebrew chỉ vì chúng có hướng RTL.

Có thể kiểm tra các Bidi_Control code point trong dữ liệu đến bằng cách duyệt theo Unicode code point:

    static boolean isBidiControl(int codePoint) {
        return codePoint == 0x061C
                || codePoint == 0x200E
                || codePoint == 0x200F
                || (codePoint >= 0x202A && codePoint <= 0x202E)
                || (codePoint >= 0x2066 && codePoint <= 0x2069);
    }

    static void reportBidiControls(String text) {
        for (int offset = 0; offset < text.length();) {
            int codePoint = text.codePointAt(offset);

            if (isBidiControl(codePoint)) {
                System.out.printf(
                        "Bidi control U+%04X at UTF-16 offset %d%n",
                        codePoint,
                        offset
                );
            }

            offset += Character.charCount(codePoint);
        }
    }

Đoạn code trên phát hiện các ký tự điều khiển hướng phổ biến theo danh sách Bidi_Control của Unicode. Nó không đánh giá một chuỗi là độc hại hay hợp lệ. Hãy dùng kết quả để log, review hoặc áp dụng policy theo trường dữ liệu. Nếu cần hiển thị an toàn, escape các control character trong log thay vì để terminal tự sắp xếp lại toàn bộ thông điệp.

## 11. Các lỗi triển khai cần tránh

- **Đảo toàn bộ chuỗi RTL:** làm hỏng thứ tự số, dấu câu, dấu kết hợp và đoạn LTR nhúng.
- **Lưu visual order:** khiến tìm kiếm, so sánh, copy/paste, parsing và trao đổi dữ liệu không nhất quán.
- **Coi run order là visual order:** `getRunStart/Limit/Level` trả các run theo logical order; cần bố trí theo level.
- **Đảo từng ký tự trong run RTL:** Bidi không yêu cầu tự đảo String; shaping và glyph layout cần engine phù hợp.
- **Phân tích cả tài liệu như một paragraph:** paragraph separator làm ranh giới của thuật toán; mỗi paragraph cần được xử lý độc lập.
- **Bỏ qua line-level processing:** khi text wrap thành nhiều dòng, dùng `createLineBidi` hoặc layout engine có xử lý line.
- **Dùng Bidi để tạo caret bằng offset đơn giản:** UTF-16 offset không phải visual caret position; dùng TextLayout/hit-testing.
- **Dùng `requiresBidi` như kiểm tra RTL:** phương thức có trường hợp đặc biệt với Arabic Presentation Forms và không phải validator.
- **Dùng RLO/LRO để sửa mọi lỗi hiển thị:** overrides có rủi ro gây hiểu nhầm; ưu tiên base direction rõ ràng và isolates.
- **Xóa control characters khỏi mọi dữ liệu:** có thể làm hỏng nội dung RTL hợp lệ; áp dụng policy theo loại trường.

## 12. Quy trình lựa chọn API

1. Giữ chuỗi ở logical order trong database, file, message và API.
2. Xác định thành phần hiển thị có biết base direction hay phải dùng first-strong.
3. Nếu chỉ render, ưu tiên Swing text component, Graphics2D hoặc TextLayout.
4. Nếu tự bố trí run hoặc inline object, tạo Bidi cho từng paragraph.
5. Dùng `isMixed()`, `getRunCount()`, `getRunLevel()` và các offset để phân tích.
6. Nếu cần visual order của object/run, dùng `Bidi.reorderVisually`; không đảo ký tự trong String.
7. Nếu paragraph wrap, tạo Bidi cho từng line bằng `createLineBidi` hoặc dùng LineBreakMeasurer/TextLayout.
8. Dùng shaping engine/font hỗ trợ script cần hiển thị; Bidi chỉ giải quyết hướng.
9. Kiểm tra control characters trong dữ liệu không tin cậy và áp dụng policy theo trường.
10. Kiểm thử trên các đoạn trộn RTL/LTR có số, dấu ngoặc, dấu câu, combining marks, emoji và supplementary characters.

## 13. Biên dịch và chạy trên JDK 26

`java.text.Bidi` là API ổn định từ Java 1.4, nằm trong module `java.base`. Ví dụ phân tích run không cần AWT và không cần preview:

    javac --release 26 -encoding UTF-8 -d out src/InspectBidiRuns.java
    java -cp out InspectBidiRuns

Nếu dùng `TextLayout`, `Font` hoặc `Graphics2D`, cần module `java.desktop`. Với ứng dụng modular:

    module application.ui {
        requires java.desktop;
    }

Không bật `--enable-preview`. Khi chạy trên JDK 27, các API này vẫn là API Java SE ổn định. Nếu ứng dụng cần hỗ trợ JDK cũ hơn, `java.text.Bidi` đã có từ Java 1.4; không cần thư viện ngoài chỉ để phân tích UBA cơ bản.

## Tài liệu chính thức

- [Java SE 26 API — java.text.Bidi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Bidi.html): constructor, base direction, embedding levels, runs, line Bidi, requiresBidi và reorderVisually.
- [Java SE 27 API — java.text.Bidi](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Bidi.html): xác nhận các API Bidi tiếp tục có trong JDK 27.
- [Java SE 26 API — java.awt.font.TextLayout](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/font/TextLayout.html): bidi analysis, glyph shaping/reordering, caret, hit testing và rendering.
- [Java SE 26 API — java.awt.Font.layoutGlyphVector](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Font.html): layout glyph cho một run có hướng đồng nhất và các script cần shaping.
- [Unicode Standard Annex #9 — Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/): đặc tả hiện hành của Unicode Bidirectional Algorithm, paragraph/line processing, isolates, embeddings, overrides và visual reordering.
- [Unicode FAQ — Writing Direction and Bidirectional Text](https://www.unicode.org/faq/bidi.html): giải thích strong, weak và neutral directional types.
- [Oracle — Java 2D TextLayout API](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/font/package-summary.html): các API dàn trang, ngắt dòng, shaping và hiển thị văn bản.

`java.text.Bidi` là API ổn định và vẫn áp dụng trong JDK 26/27. Hãy dùng nó khi cần phân tích run hoặc tự quản lý bố cục; với hiển thị thông thường, để text layout engine xử lý bidi, shaping và glyph placement. Giữ dữ liệu ở logical order, ưu tiên isolates cho nội dung nhúng và kiểm tra control characters ở ranh giới tin cậy.
