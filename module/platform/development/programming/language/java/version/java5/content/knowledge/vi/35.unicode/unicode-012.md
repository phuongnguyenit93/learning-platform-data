# Phân biệt xử lý code point với phân đoạn ký tự người dùng nhìn thấy

## “Một ký tự” phải được định nghĩa theo công việc

Khi cần kiểm tra Unicode, giới hạn độ dài một tên hiển thị hoặc xóa một ký tự trong trình soạn thảo, câu hỏi đầu tiên là: **đang đếm và thao tác trên đơn vị nào?**

Có ít nhất ba lớp cần phân biệt trong Java:

| Lớp | Ý nghĩa | Công cụ thường dùng |
| --- | --- | --- |
| Đơn vị mã UTF-16 | Một giá trị `char` trong API chuỗi | `length()`, `charAt`, chỉ số `substring` |
| Mã điểm Unicode — code point | Một giá trị số trong không gian Unicode | `codePointAt`, `codePointCount`, `codePoints()` |
| Cụm tự vị mở rộng — extended grapheme cluster | Nhóm mã điểm được phân đoạn để gần với một ký tự người dùng cảm nhận | Bộ phân đoạn grapheme, chẳng hạn regex `\X` của Java |

Đi theo mã điểm giúp không chia đôi cặp surrogate hợp lệ. Tuy nhiên, một cụm tự vị có thể gồm nhiều mã điểm, nên thao tác đúng theo mã điểm vẫn có thể tách dấu kết hợp hoặc làm vỡ một chuỗi emoji.

Unicode UAX #29 định nghĩa các quy tắc phân đoạn mặc định cho cụm tự vị, từ và câu. Cụm tự vị là đơn vị hữu ích để mô hình hóa ký tự người dùng cảm nhận, không phải phép đếm trực tiếp số hình vẽ do font tạo ra. [Unicode UAX #29](https://www.unicode.org/reports/tr29/).

Bài này dùng ví dụ Java 17+ và cách phân đoạn vẫn áp dụng trong Java hiện đại.

## Các ví dụ cho thấy ba phép đếm khác nhau

### Chữ có dấu có thể gồm hai mã điểm

Chữ `á` có thể được biểu diễn bằng:

```text
U+00E1
```

hoặc:

```text
U+0061 + U+0301
a         dấu sắc kết hợp
```

Dạng thứ hai có hai mã điểm nhưng thường được người đọc cảm nhận như một chữ có dấu. Nếu chỉ giữ mã điểm đầu, kết quả còn `a` và đã mất dấu. Không cặp surrogate nào bị cắt, nhưng hình thức chữ ban đầu vẫn bị thay đổi.

### Một mã điểm ngoài BMP vẫn có thể là một cụm

Biểu tượng tên lửa `U+1F680` là một mã điểm, được biểu diễn bằng hai đơn vị UTF-16. Trong ví dụ này, nó là một cụm tự vị.

Vì vậy, hai đơn vị `char` không nhất thiết là hai mã điểm, và hai mã điểm cũng không nhất thiết là hai cụm tự vị.

### Một chuỗi emoji có thể gồm nhiều mã điểm

Những cấu trúc thường gặp:

- Emoji nền kết hợp dấu điều chỉnh màu da.
- Cặp regional indicator biểu diễn một lá cờ.
- Chuỗi emoji nối bằng `U+200D`, gọi là Zero Width Joiner — ZWJ.
- Ký tự kết hợp variation selector, chẳng hạn `U+FE0F` để yêu cầu cách trình bày emoji trong các trường hợp phù hợp.

Các thành phần đó vẫn là những mã điểm riêng, dù bộ phân đoạn nhận cả nhóm thành một cụm. Cách hiển thị cuối còn phụ thuộc font và hệ thống dựng chữ; máy thiếu hỗ trợ có thể vẽ nhiều hình riêng thay vì hình ghép.

## Chọn lớp xử lý theo ý nghĩa của thao tác

**Xử lý theo mã điểm** phù hợp khi kiểm tra thuộc tính Unicode của từng thành phần, chẳng hạn phân loại chữ/số, quan sát danh sách mã điểm hoặc thực hiện một phép biến đổi được định nghĩa trên mã điểm.

**Phân đoạn theo cụm tự vị** phù hợp khi cần lấy tiền tố để hiển thị, di chuyển ranh giới chọn văn bản hoặc triển khai quy tắc “giữ nguyên một ký tự người dùng cảm nhận”.

Không nên lấy `codePointCount` rồi đặt nhãn giao diện “số ký tự nhìn thấy” mà chưa định nghĩa hợp đồng. Tương tự, quy tắc “tối đa 20 ký tự” giữa giao diện và máy chủ cần thống nhất đơn vị, thay vì bên này đếm `char` còn bên kia đếm grapheme.

Cụm tự vị không thay thế tất cả đơn vị khác: giới hạn dung lượng lưu trữ có thể tính bằng byte sau mã hóa; chỉ số Java vẫn cần tính bằng UTF-16; thuật toán Unicode có thể làm việc theo mã điểm.

## Java regex hỗ trợ \X để lấy từng cụm

Trong `Pattern`, regex `\X` khớp một **Unicode extended grapheme cluster**. Vì chuỗi Java cũng dùng dấu gạch chéo ngược làm ký tự escape, mã nguồn cần viết:

```java
Pattern pattern = Pattern.compile("\\X");
```

Không viết `"\X"`: đó không phải escape hợp lệ trong chuỗi Java. Dùng `Matcher.find()` để lần lượt lấy từng cụm; `start()` và `end()` vẫn trả vị trí UTF-16 dùng được với `substring`.

Cú pháp `\X` được tài liệu hóa ở cả Java 17 và Java hiện hành. Quy tắc và dữ liệu Unicode cụ thể đi kèm phiên bản JDK đang chạy; không suy ra rằng mọi JDK tự động dùng bản Unicode mới nhất. [Java SE 17: Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 25: Pattern](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html).

## Chương trình kiểm chứng đầy đủ

Lưu thành `GraphemeDemo.java`. Các chuỗi dùng escape Unicode và kết quả dùng số hệ mười sáu, nên không cần dựa vào khả năng hiển thị emoji của terminal.

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class GraphemeDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static int graphemeCount(String text) {
        int count = 0;
        Matcher matcher = GRAPHEME.matcher(text);
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private static String takeGraphemes(String text, int max) {
        if (max < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        Matcher matcher = GRAPHEME.matcher(text);
        int end = 0;
        for (int count = 0; count < max && matcher.find(); count++) {
            end = matcher.end();
        }
        return text.substring(0, end);
    }

    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String name, String text) {
        System.out.println(name + ": units=" + text.length()
                + ", codePoints=" + text.codePointCount(0, text.length())
                + ", graphemes=" + graphemeCount(text));
    }

    public static void main(String[] args) {
        String composed = "\u00E1";
        String decomposed = "a\u0301";
        String rocket = "\uD83D\uDE80";
        String skinTone = "\uD83D\uDC4D\uD83C\uDFFD";
        String flag = "\uD83C\uDDFB\uD83C\uDDF3";
        String family = "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                + "\uD83D\uDC67\u200D\uD83D\uDC66";
        String heart = "\u2764\uFE0F";

        show("composed", composed);
        show("decomposed", decomposed);
        show("rocket", rocket);
        show("skin tone", skinTone);
        show("flag", flag);
        show("family", family);
        show("heart variation", heart);

        int end = decomposed.offsetByCodePoints(0, 1);
        String byCodePoint = decomposed.substring(0, end);
        System.out.println("one code point: " + codePoints(byCodePoint));
        System.out.println("one grapheme: " + codePoints(takeGraphemes(decomposed, 1)));

        String mixed = decomposed + rocket + "B";
        Matcher matcher = GRAPHEME.matcher(mixed);
        while (matcher.find()) {
            System.out.println("cluster [" + matcher.start() + "," + matcher.end()
                    + "): " + codePoints(matcher.group()));
        }
        System.out.println("first two clusters: " + codePoints(takeGraphemes(mixed, 2)));
        System.out.println("zero limit length: " + takeGraphemes(mixed, 0).length());
        System.out.println("large limit keeps all: " + mixed.equals(takeGraphemes(mixed, 99)));
        System.out.println("empty cluster count: " + graphemeCount(""));

        System.out.println("raw equals: " + composed.equals(decomposed));
        String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals: " + composed.equals(normalized));
        show("NFC decomposed", normalized);
        show("NFC family", Normalizer.normalize(family, Normalizer.Form.NFC));

        try {
            takeGraphemes(mixed, -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative limit rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 GraphemeDemo.java
java GraphemeDemo
```

Stdout kiểm chứng:

```text
composed: units=1, codePoints=1, graphemes=1
decomposed: units=2, codePoints=2, graphemes=1
rocket: units=2, codePoints=1, graphemes=1
skin tone: units=4, codePoints=2, graphemes=1
flag: units=4, codePoints=2, graphemes=1
family: units=11, codePoints=7, graphemes=1
heart variation: units=2, codePoints=2, graphemes=1
one code point: 0061
one grapheme: 0061 0301
cluster [0,2): 0061 0301
cluster [2,4): 1F680
cluster [4,5): 0042
first two clusters: 0061 0301 1F680
zero limit length: 0
large limit keeps all: true
empty cluster count: 0
raw equals: false
NFC equals: true
NFC decomposed: units=1, codePoints=1, graphemes=1
NFC family: units=11, codePoints=7, graphemes=1
negative limit rejected
```

## Phân tích những điều chương trình chứng minh

### Các số đếm không thể dùng thay nhau

Hai hàng đầu cùng có một grapheme nhưng số mã điểm khác nhau. Hàng tên lửa có một mã điểm nhưng hai đơn vị UTF-16. Chuỗi gia đình có bảy mã điểm, mười một đơn vị UTF-16 và được nhận thành một grapheme.

Một bảng quy đổi cố định như “một grapheme bằng hai char” sẽ sai với chính các dữ liệu này. Không có số `char` hoặc số mã điểm cố định cho mọi cụm tự vị.

Dữ liệu `flag` là hai regional indicator cho cờ Việt Nam. Dữ liệu `skinTone` là emoji ngón tay cái và dấu điều chỉnh màu da. Dữ liệu `family` có bốn mã điểm biểu tượng và ba ZWJ. Những thành phần này giúp kiểm tra các cơ chế ghép khác nhau, thay vì chỉ thử chữ Latin không dấu.

### Cắt một mã điểm có thể làm mất dấu

Hai dòng:

```text
one code point: 0061
one grapheme: 0061 0301
```

cho thấy khác biệt cụ thể. Đoạn dùng `offsetByCodePoints` giữ đúng một mã điểm, nên chỉ còn `a`. Hàm `takeGraphemes` giữ một cụm đầy đủ, nên vẫn có `a` cùng dấu sắc.

Cả hai thuật toán đều thực hiện đúng đơn vị mà nó được yêu cầu xử lý. Lỗi nằm ở việc chọn một thuật toán đếm mã điểm cho yêu cầu cần giữ nguyên cụm hiển thị.

### Ranh giới grapheme được chuyển thành chỉ số UTF-16

`mixed` chứa chữ có dấu dạng phân rã, tên lửa và `B`. Bộ phân đoạn cho ba khoảng:

| Khoảng UTF-16 | Nội dung theo mã điểm |
| --- | --- |
| `[0,2)` | `0061 0301` |
| `[2,4)` | `1F680` |
| `[4,5)` | `0042` |

Điểm kết thúc cụm thứ hai là 4, nên `substring(0, 4)` giữ trọn hai cụm đầu. Bạn không truyền “2 grapheme” trực tiếp cho `substring`; trước hết phải tìm chỉ số UTF-16 tương ứng.

## Cách hàm takeGraphemes xử lý giới hạn

Hàm đếm tối đa `max` lần khớp và nhớ `matcher.end()` của lần cuối. Sau đó nó lấy tiền tố đến ranh giới ấy.

- `max = 0`: chưa nhận cụm nào, điểm kết thúc bằng 0, kết quả rỗng.
- Chuỗi rỗng: không có lần khớp, kết quả rỗng.
- `max` lớn hơn số cụm: kết quả giữ toàn bộ chuỗi.
- `max` âm: báo lỗi rõ ràng.
- Tiền tố kết thúc tại ranh giới do bộ phân đoạn cung cấp.

Hàm chỉ trả tiền tố; nó không thêm dấu ba chấm. Nếu sản phẩm cần dấu ba chấm và giới hạn tổng độ dài hiển thị, phải định nghĩa dấu thêm vào có tính trong giới hạn hay không.

`Pattern` được tạo một lần để tái sử dụng; mỗi lời gọi tạo `Matcher` riêng. Không dùng chung một `Matcher` đang thay đổi giữa các lần xử lý đồng thời.

Đừng tự thay bộ phân đoạn bằng quy tắc “một ký tự nền rồi gom mọi dấu kết hợp”. Quy tắc đó không bao quát cờ, ZWJ và các nhóm Unicode khác được minh họa trong chương trình.

## Chuẩn hóa và phân đoạn là hai công việc khác nhau

Hai chuỗi `"\u00E1"` và `"a\u0301"` có thể tương đương về mặt chuẩn tắc nhưng `String.equals` ban đầu trả về `false`, vì biểu diễn UTF-16 khác nhau.

`Normalizer.normalize(..., NFC)` đưa dữ liệu về dạng chuẩn hóa kết hợp theo quy tắc Unicode. Trong ví dụ, nó biến dạng phân rã thành cùng biểu diễn với dạng dựng sẵn, nên `NFC equals` bằng `true`. [Java SE 25: Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html).

Tuy nhiên, chuẩn hóa không có nhiệm vụ biến mọi grapheme thành một mã điểm. Chuỗi gia đình sau NFC vẫn có bảy mã điểm và một grapheme. Bởi vậy, không thể giải quyết mọi bài toán cắt ký tự hiển thị bằng cách “chuẩn hóa trước rồi đếm code point”.

Nếu cần vừa so sánh theo một chính sách chuẩn hóa, vừa cắt theo cụm, hãy xác định thứ tự xử lý và tính các chỉ số trên **đúng phiên bản chuỗi sẽ được cắt**. Chỉ số tính trên dạng phân rã không nên dùng lại nguyên xi sau khi chuẩn hóa làm thay đổi độ dài UTF-16.

Không mặc định bỏ dấu kết hợp để đơn giản hóa số đếm. Làm vậy thay đổi nội dung, đặc biệt với văn bản tiếng Việt.

## Những giới hạn cần hiểu khi đưa vào sản phẩm

### Grapheme không phải độ rộng hiển thị

Một cụm có thể được vẽ bằng nhiều glyph hoặc được ghép thành một glyph tùy font. Một ký tự CJK, một emoji và một chữ Latin có thể có độ rộng khác nhau. Đếm grapheme không cho biết chiều rộng pixel, số cột terminal hay số dòng sau khi xuống dòng.

Nếu mục tiêu là vừa một vùng giao diện, cần đo hoặc bố trí bằng hệ thống dựng chữ của giao diện. Nếu mục tiêu là giới hạn chuỗi theo đơn vị cảm nhận, grapheme là một đơn vị phù hợp để định nghĩa hợp đồng.

### Phải giữ bối cảnh khi phân đoạn

Nối các phần văn bản có thể làm thay đổi ranh giới. Ví dụ, phần thứ nhất là `a`, phần thứ hai là `U+0301`. Xử lý riêng từng phần không cho phép cộng kết quả đếm rồi coi đó là số cụm của chuỗi đã nối; khi nối lại, dấu có thể thuộc cùng cụm với `a`.

Với dữ liệu truyền theo khối, không nên coi cuối mọi khối là ranh giới grapheme cuối cùng. Cần thiết kế xử lý phần còn chờ để xem bối cảnh tiếp theo, hoặc phân đoạn trên chuỗi hoàn chỉnh khi quy mô dữ liệu cho phép.

### Phiên bản thuật toán và dữ liệu phải được kiểm chứng

Những cụm xuất hiện trong ví dụ đã có hành vi ổn định trên runtime dùng để chạy chương trình. Với ký tự mới, chữ viết phức tạp hoặc yêu cầu tuân thủ một phiên bản Unicode cụ thể, cần ghi nhận JDK thực tế và thử bộ dữ liệu đại diện trên runtime sẽ triển khai.

Nếu giao diện và máy chủ dùng các bộ phân đoạn hoặc phiên bản dữ liệu khác nhau, có thể có trường hợp biên đếm khác nhau. Quy tắc sản phẩm cần xác định nơi quyết định cuối cùng và kiểm tra tính nhất quán.

Một grapheme cũng có thể chứa nhiều mã điểm, nên giới hạn số grapheme không tự tạo ra một giới hạn byte lưu trữ. Nếu cần cả hai ràng buộc, hãy kiểm tra cả hai theo đơn vị đã công bố.

### Phân đoạn không thay thế xác thực dữ liệu

Các ví dụ dùng chuỗi Unicode được tạo hợp lệ. `\X` trong bài được dùng để tìm ranh giới cụm, không để khẳng định dữ liệu đầu vào đã vượt qua mọi yêu cầu xác thực. Chính sách đối với surrogate đứng riêng hoặc lỗi giải mã vẫn cần được xác định tại lớp nhập dữ liệu.

## Thực hành

1. Thay giới hạn tiền tố của `mixed` từ 2 thành 1 và 3; đối chiếu chỉ số UTF-16 với nội dung mã điểm thực tế.
2. Thử cắt chuỗi màu da sau một mã điểm và sau một grapheme; nêu phần ý nghĩa bị thay đổi.
3. Viết hàm bỏ cụm cuối cùng bằng cách tìm ranh giới cuối, rồi kiểm tra với chuỗi rỗng, chữ có dấu, cờ và chuỗi ZWJ.
4. So sánh số mã điểm trước và sau NFC cho chữ có dấu; kiểm tra vì sao kết luận “NFC làm mọi grapheme chỉ còn một mã điểm” không đúng.
5. Định nghĩa rõ yêu cầu “tối đa 20 ký tự” cho một trường tên hiển thị: đơn vị nào được dùng, khi nào chuẩn hóa và có cần giới hạn byte riêng không.

Quy tắc lựa chọn là: xử lý mã điểm khi thuật toán nói về thành phần Unicode; tìm ranh giới grapheme khi thao tác cần giữ nguyên cụm ký tự mà người dùng cảm nhận.
