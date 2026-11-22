# Cắt văn bản theo cụm ký tự bằng BreakIterator trong Java

## Mục tiêu

Một người dùng nhập chữ **ắ**, nhưng trong bộ nhớ chuỗi đó có thể được biểu diễn bằng **một code point** `U+1EAF` hoặc bằng **ba code point** `U+0061 U+0306 U+0301` (chữ `a`, dấu breve, dấu sắc). Tương tự, một emoji có thể dùng hai UTF-16 code unit, còn emoji phức hợp có thể gồm nhiều code point ghép lại.

Nếu cắt văn bản bằng `substring(0, n)`, `charAt` hoặc chỉ đếm `codePoints()`, bạn có thể cắt giữa một dấu kết hợp và chữ cơ sở, giữa hai nửa surrogate pair, hoặc giữa các thành phần của một emoji. Kết quả thường là dấu đứng lẻ, biểu tượng bị tách hay chữ không còn như người dùng mong đợi.

Để tìm ranh giới **cụm ký tự** theo thuật toán phân đoạn text của Java, ta dùng **`java.text.BreakIterator.getCharacterInstance(Locale)`**. Đây là bài thực hành tổng hợp về xử lý Unicode, localization và cắt chuỗi an toàn hơn trong Java Core.

Sau bài, bạn có thể:

- Phân biệt **UTF-16 code unit**, **Unicode code point** và **grapheme cluster** (cụm ký tự thường được cảm nhận như một đơn vị hiển thị).
- Giải thích vì sao `String.length()`, `String.codePointCount(...)` và số cụm ký tự có thể khác nhau.
- Dùng `BreakIterator.getCharacterInstance(locale)`, `setText`, `first`, `next` và `DONE` để duyệt ranh giới trong `String`.
- Cắt prefix/giới hạn độ dài theo số cụm thay vì theo `char`, giữ nguyên thứ tự và nội dung gốc.
- Hiểu chính xác tính chất **start-inclusive/end-exclusive** của offsets trả về bởi BreakIterator.
- Dùng `isBoundary`, `preceding` và `following` khi cần điều chỉnh điểm cắt hoặc vị trí con trỏ.
- Nhận diện khác biệt giữa character breaks, word/sentence/line breaks, cũng như `Pattern.compile("\\X")` và BreakIterator.
- Thiết kế kiểm thử cho chữ tiếng Việt NFC/NFD, surrogate pair, emoji modifiers, ZWJ sequence và regional indicator.
- Hiểu giới hạn theo **phiên bản JDK, Unicode data và implementation provider** trước khi tuyên bố cắt đúng mọi grapheme hiện đại.

Bài tập trung vào **cắt văn bản theo cụm ký tự**; không biến thuật toán phân đoạn thành kiểm tra chính tả, đo độ rộng glyph hoặc một trình vẽ chữ hoàn chỉnh.

## 1. Một ký tự người dùng thấy khác với một char Java

Trong Java, `String` sử dụng mã hóa UTF-16 ở mức API:

- `String.length()` trả **số UTF-16 code unit**. Kiểu `char` mang một code unit 16-bit; một code point ngoài BMP thường cần hai `char` tạo surrogate pair.
- `codePointCount(0, length())` trả **số code point Unicode**.
- **Grapheme cluster**, đặc biệt *extended grapheme cluster* theo Unicode Text Segmentation, là một nhóm code point mà người dùng thường cảm nhận như một ký tự hiển thị.

Ba phép đếm **không tương đương**.

### Chữ tiếng Việt dạng phân rã

Chữ `ắ` có thể được tạo:

```java
String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";
```

Đây là đoạn minh họa trong một phương thức. Dạng ghép sẵn `composed` có `length() == 1` và một code point. Dạng phân rã `decomposed` có `length() == 3` và ba code point. Nhưng một thuật toán phân đoạn theo grapheme thích hợp thường xem mỗi chuỗi là **một cụm ký tự**.

Nếu gọi:

```java
String broken = decomposed.substring(0, 1);
```

`broken` chỉ còn `a`, hai dấu bị bỏ. Phép cắt này không làm hỏng UTF-16, nhưng **làm mất thông tin dấu** và tạo một đoạn text khác với thứ người dùng đã nhập.

Nếu gọi:

```java
String suffix = decomposed.substring(1);
```

`suffix` bắt đầu bằng hai dấu kết hợp không còn chữ cơ sở. Font hoặc renderer có thể vẽ chúng ở vị trí bất thường. Đây là lý do không cắt theo chỉ số `char` tùy ý nếu đơn vị nghiệp vụ là “chữ người dùng nhìn thấy”.

### Emoji và surrogate pair

Emoji `😀` là code point `U+1F600`, có hai UTF-16 code unit:

```java
String emoji = "\uD83D\uDE00";
System.out.println(emoji.length());
System.out.println(emoji.codePointCount(0, emoji.length()));
```

Stdout:

```text
2
1
```

Cắt `emoji.substring(0, 1)` giữ lại một **high surrogate** không ghép đủ cặp. Đây là vấn đề khác với dấu tiếng Việt, nhưng cùng cho thấy `length()` không diễn đạt đúng đơn vị ký tự nhìn thấy.

Duyệt `codePoints()` giúp không tách nửa surrogate pair; tuy vậy nó vẫn có thể chia chữ `a + ◌̆ + ◌́` thành ba code point riêng. Đếm code point là một bước tiến so với đếm `char`, nhưng **không tự thành thuật toán phân đoạn grapheme**.

## 2. BreakIterator cung cấp những loại ranh giới nào?

`java.text.BreakIterator` là lớp trừu tượng đại diện cho một bộ xác định ranh giới text. Java có những factory tiêu biểu:

| Factory | Đơn vị phân đoạn | Bài toán điển hình |
| --- | --- | --- |
| `getCharacterInstance(locale)` | Ranh giới cụm ký tự | Cắt/truncation theo cụm, điều chỉnh caret |
| `getWordInstance(locale)` | Ranh giới liên quan từ | Điều hướng từng từ, tokenization mức cơ bản |
| `getSentenceInstance(locale)` | Ranh giới câu | Chia câu theo quy tắc locale |
| `getLineInstance(locale)` | Ranh giới ngắt dòng | Xác định các điểm có thể ngắt dòng |

**Phải chọn đúng factory.** Nếu mục tiêu là “lấy 5 ký tự người dùng nhìn thấy”, `getCharacterInstance` là lựa chọn cần khảo sát; `getWordInstance` không trả một break cho mỗi chữ, còn `getLineInstance` là về khả năng wrap dòng chứ không phải cắt độ dài theo chữ.

Cũng đừng coi một *grapheme cluster* luôn là một từ, âm tiết hoặc glyph. Trong typography, nhiều cụm có thể tạo một ligature, hoặc một cụm cần nhiều glyph. BreakIterator giúp phân tích biên text, **không đo chiều rộng hiển thị**.

### Chọn Locale

Ví dụ:

```java
import java.text.BreakIterator;
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
BreakIterator iterator =
        BreakIterator.getCharacterInstance(vietnamese);
```

Việc truyền locale tường minh giúp biểu đạt ngữ cảnh sử dụng và tránh phụ thuộc default locale. Tuy nhiên, không nên giả định mọi kết quả character break đều khác nhau giữa tiếng Việt và tiếng Anh; nhiều quy tắc cụm ký tự dựa vào thuộc tính Unicode chung. Tác động của locale/provider rõ hơn với phân đoạn từ, câu hoặc line.

**Không suy từ locale để bỏ/đổi dấu.** Chữ tiếng Việt dạng NFD vẫn là dữ liệu chứa dấu kết hợp; BreakIterator chỉ tìm biên, không chuyển NFD thành NFC.

## 3. Cơ chế di chuyển qua các boundary

Khi tạo iterator, chưa có chuỗi nào được phân tích. Cần gọi `setText`:

```java
BreakIterator it =
        BreakIterator.getCharacterInstance(Locale.forLanguageTag("vi-VN"));
it.setText(text);
```

Với `text` là `String` không null. Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `setText(String)` | Chọn chuỗi đầu vào để phân đoạn |
| `first()` | Đưa con trỏ về boundary đầu, thường index 0 |
| `last()` | Đưa con trỏ về boundary cuối, thường là `text.length()` |
| `next()` | Đi tới boundary kế tiếp; hết thì trả `BreakIterator.DONE` |
| `previous()` | Đi tới boundary trước đó |
| `current()` | Đọc boundary hiện tại, không tự di chuyển |
| `following(offset)` | Boundary **sau** offset đã cho |
| `preceding(offset)` | Boundary **trước** offset đã cho |
| `isBoundary(offset)` | Kiểm tra một offset có đúng boundary không |
| `next(int n)` | Di chuyển `n` boundaries, có thể theo chiều ngược nếu n âm |
| `DONE` | Giá trị sentinel cho trạng thái không còn boundary |

Một cách duyệt phổ biến:

```java
for (int start = it.first(), end = it.next();
     end != BreakIterator.DONE;
     start = end, end = it.next()) {
    String cluster = text.substring(start, end);
    // Xử lý một cụm vừa tách được.
}
```

Đây là snippet bên trong phương thức có `it` đã được `setText(text)`. Mỗi lần lặp sử dụng một khoảng **nửa mở** `[start, end)`:

- `start` là offset thuộc cụm.
- `end` là offset **ngay sau** phần tử cuối của cụm.
- `substring(start, end)` lấy đúng đoạn ký tự của cụm.

Đừng thêm `+1` vào `end`: `String.substring` cũng dùng end-exclusive.

### Offsets là UTF-16, không phải số code point

Một boundary là vị trí trong `String`, tức chỉ số UTF-16. Với emoji `😀`, một cụm có thể có `start=4, end=6` dù chỉ một code point. Không dùng `end` làm thứ tự trong một mảng code point mà không chuyển đổi.

Điểm mạnh là `substring(start,end)` hoạt động đúng trực tiếp với offsets của BreakIterator, bảo toàn nguyên văn cả chữ cơ sở lẫn dấu kết hợp.

## 4. Ví dụ ranh giới có thể nhìn và kiểm tra được

Lấy chuỗi:

```java
String text = "A" + "a\u0306\u0301" + "\uD83D\uDE00" + "B";
```

Dãy Unicode logic:

```text
A         U+0041
a         U+0061
breve     U+0306
acute     U+0301
😀        U+1F600 (surrogate pair trong UTF-16)
B         U+0042
```

Tổng cộng:

- **7 UTF-16 code unit**: A (1) + a (1) + hai dấu (2) + emoji (2) + B (1).
- **6 Unicode code point**: A, a, breve, acute, emoji, B.
- **4 grapheme cluster** theo dữ liệu JDK kiểm thử: A, `a + breve + acute`, emoji, B.

BreakIterator character theo locale vi-VN trong môi trường kiểm thử trả:

| Cụm | UTF-16 start | UTF-16 end | Code point nằm trong cụm |
| --- | ---: | ---: | --- |
| `A` | 0 | 1 | `U+0041` |
| `a + ◌̆ + ◌́` | 1 | 4 | `U+0061 U+0306 U+0301` |
| `😀` | 4 | 6 | `U+1F600` |
| `B` | 6 | 7 | `U+0042` |

Nếu người dùng yêu cầu lấy **hai cụm đầu**, prefix đúng là chuỗi:

```text
A + a + U+0306 + U+0301
```

có **4 UTF-16 code unit**. `substring(0, 2)` không cho cùng kết quả: nó mới lấy A và chữ a, bỏ hai dấu; `substring(0, 4)` mới trùng ranh giới ở ví dụ cụ thể, nhưng số `4` không được hard-code cho mọi đầu vào.

### Vì sao không normalize NFC trước rồi cắt theo char?

`Normalizer.normalize(text, NFC)` có thể ghép chữ `a + breve + acute` thành `ắ`, giúp một số ví dụ bớt số code unit. Nhưng nó **không biến mọi grapheme thành một `char`**, nhất là emoji ngoài BMP, emoji ZWJ, cờ, chữ kết hợp của nhiều hệ chữ.

Hơn nữa, chuẩn hóa Unicode làm thay đổi cách biểu diễn code point, dù giữ canonical equivalence. Nếu ứng dụng cần giữ nguyên text đã nhập, nên **cắt theo boundary mà không tự rewrite sang NFC**. Có thể có chính sách chuẩn hóa riêng ở ranh giới lưu trữ, nhưng đó là một quyết định khác với segmentation.

## 5. Chương trình Java 17+ đầy đủ: tách và lấy prefix

Tạo file `GraphemeBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public final class GraphemeBreakDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private GraphemeBreakDemo() {}

    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static List<String> splitClusters(String text, Locale locale) {
        BreakIterator it = BreakIterator.getCharacterInstance(locale);
        it.setText(text);

        List<String> result = new ArrayList<>();
        for (int start = it.first(), end = it.next();
             end != BreakIterator.DONE;
             start = end, end = it.next()) {
            result.add(text.substring(start, end));
        }
        return result;
    }

    public static String takeClusters(
            String text, int maxClusters, Locale locale) {
        if (maxClusters < 0) {
            throw new IllegalArgumentException("Negative count");
        }
        if (maxClusters == 0 || text.isEmpty()) {
            return "";
        }

        BreakIterator it = BreakIterator.getCharacterInstance(locale);
        it.setText(text);
        int end = it.first();

        for (int i = 0; i < maxClusters; i++) {
            int next = it.next();
            if (next == BreakIterator.DONE) {
                break;
            }
            end = next;
        }
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A" + "a\u0306\u0301"
                + "\uD83D\uDE00" + "B";

        System.out.println("utf16=" + text.length());
        System.out.println("codepoints="
                + text.codePointCount(0, text.length()));

        BreakIterator it = BreakIterator.getCharacterInstance(VI);
        it.setText(text);

        int count = 0;
        for (int start = it.first(), end = it.next();
             end != BreakIterator.DONE;
             start = end, end = it.next()) {
            count++;
            System.out.println("[" + start + "," + end + ") "
                    + codePoints(text.substring(start, end)));
        }

        System.out.println("clusters=" + count);
        System.out.println("take2="
                + codePoints(takeClusters(text, 2, VI)));

        BreakIterator edge =
                BreakIterator.getCharacterInstance(VI);
        edge.setText(text);

        System.out.println("at5=" + edge.isBoundary(5)
                + ",following5=" + edge.following(5)
                + ",preceding5=" + edge.preceding(5));

        System.out.println("split count="
                + splitClusters(text, VI).size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GraphemeBreakDemo.java
java GraphemeBreakDemo
```

Stdout xác định trong JDK được dùng để kiểm tra, với locale vi-VN:

```text
utf16=7
codepoints=6
[0,1) U+0041
[1,4) U+0061 U+0306 U+0301
[4,6) U+1F600
[6,7) U+0042
clusters=4
take2=U+0041 U+0061 U+0306 U+0301
at5=false,following5=6,preceding5=4
split count=4
```

### Giải thích

1. `utf16=7` và `codepoints=6` khác nhau vì emoji `U+1F600` có hai code unit UTF-16.
2. `[1,4)` giữ nguyên cả chữ `a` và hai combining marks, không bỏ dấu.
3. `[4,6)` giữ nguyên surrogate pair của emoji.
4. `takeClusters(text, 2, VI)` trả prefix gồm hai cụm: A và chữ a có hai dấu, tổng cộng bốn code unit.
5. Offset 5 nằm **giữa hai code unit của emoji**, nên `edge.isBoundary(5)` là false; boundary kế sau là 6, ngay trước là 4.
6. `splitClusters` tạo danh sách các cụm theo thứ tự logic, không cần chuẩn hóa NFC và không đảo code point.
7. Phần print code point dùng ký tự ASCII nên test vẫn đọc được ngay cả khi terminal không hỗ trợ glyph emoji hoặc chữ có dấu.

Ví dụ kiểm chứng mô hình phân đoạn đơn giản trên JDK hiện có; với những chuỗi Unicode phức tạp hơn, cần test trên **đúng phiên bản JDK/provider chạy production**.

## 6. Thiết kế hàm cắt có hợp đồng rõ ràng

Hàm `takeClusters` minh họa một policy: nhận tối đa `maxClusters` cụm từ đầu text, **không tách ranh giới** và **giữ nguyên từng code unit của phần trả về**.

Những trường hợp nên quy định:

| Đầu vào | Kết quả/phản ứng |
| --- | --- |
| `text = ""` | Trả chuỗi rỗng |
| `maxClusters = 0` | Trả chuỗi rỗng |
| `maxClusters` lớn hơn số cụm | Trả toàn bộ text |
| `maxClusters` âm | Ném `IllegalArgumentException` |
| `text == null` | Nên quy định lỗi rõ; demo để `NullPointerException` từ lời gọi API nếu chưa kiểm tra |
| `locale == null` | Nên từ chối/kiểm tra rõ thay vì mặc định ngầm |

Nếu dùng trong API public, nên thêm `Objects.requireNonNull(text, "text")` và `Objects.requireNonNull(locale, "locale")` để thông báo lỗi rõ. Đừng tự biến `null` thành `""` trừ khi đó là contract của ứng dụng.

### Cắt và thêm dấu ba chấm

Một số UI muốn giới hạn số cụm và thêm `…` nếu có phần dư. Cần quyết định **dấu ba chấm có tính trong budget không**.

Ví dụ budget 5 cụm:

- Nếu chỉ giới hạn **nội dung gốc** 5 cụm rồi append `…`, kết quả có thể là **6 cụm**.
- Nếu giới hạn **toàn output** 5 cụm, hãy lấy tối đa 4 cụm nội dung cộng `…` khi phải truncate.
- Nếu `maxClusters = 0`, trả `""`, không thêm ellipsis.
- Nếu không có phần dư, trả text gốc, không thêm dấu ba chấm.

Một helper minh họa policy **dấu ba chấm nằm trong tổng budget**:

```java
static String ellipsize(
        String text, int maxClusters, Locale locale) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("Negative limit");
    }

    List<String> clusters = GraphemeBreakDemo.splitClusters(
            text, locale);

    if (clusters.size() <= maxClusters) {
        return text;
    }
    if (maxClusters == 0) {
        return "";
    }

    String prefix = String.join(
            "", clusters.subList(0, maxClusters - 1));
    return prefix + "\u2026";
}
```

Đây là **phương thức minh họa trong cùng package hoặc lớp có thể truy cập `GraphemeBreakDemo`** và đã import `List`/`Locale`. Nó giả định dấu `…` là một cụm, phù hợp trường hợp minh họa. Nếu UI đặt giới hạn theo pixel, đây vẫn **không phải thuật toán đo độ rộng chữ**.

### Cắt mà không phải tạo list toàn bộ

`splitClusters` dễ hiểu nhưng tạo một `String` mới cho từng cụm và một `List` để lưu chúng. Nếu chỉ cần lấy **n cụm đầu**, hàm `takeClusters` có thể dừng sau `n` boundaries, tránh cấp phát một danh sách cho toàn bộ text.

Ngược lại, khi cần xử lý từng cụm (ví dụ đếm, kiểm tra, tô màu), một vòng lặp `for` qua iterator có thể xử lý trực tiếp từng đoạn `substring(start,end)` mà không cần tạo danh sách.

## 7. Điều chỉnh điểm cắt tùy ý theo boundary

Một UI có thể nhận offset từ con trỏ, tìm kiếm hoặc thao tác chọn rồi muốn đưa offset đó về ranh giới cụm gần nhất.

Ví dụ:

```java
BreakIterator edge = BreakIterator.getCharacterInstance(
        Locale.forLanguageTag("vi-VN"));
edge.setText(text);
boolean safe = edge.isBoundary(offset);
```

Đây là đoạn minh họa trong phương thức có `text` và `offset` hợp lệ. Nếu `safe` là false, `offset` đang nằm **giữa một cụm** theo quy tắc iterator.

Có thể dùng:

- `preceding(offset)`: tìm boundary **nhỏ hơn** offset.
- `following(offset)`: tìm boundary **lớn hơn** offset.
- `isBoundary(offset)`: kiểm tra offset có phải một boundary hay không.

Chú ý `preceding` và `following` tìm boundary **nghiêm ngặt trước/sau**, không đơn giản là floor/ceiling bao gồm chính offset. Nếu muốn snap offset về **boundary gần nhất không vượt quá offset**, trước tiên kiểm tra `isBoundary(offset)`; nếu true thì giữ nguyên, nếu false mới gọi `preceding(offset)`.

Ví dụ với chuỗi demo có emoji ở `[4,6)`:

```text
offset 4: đầu emoji, là boundary
offset 5: giữa surrogate pair, không phải boundary
offset 6: sau emoji, là boundary
```

Kết quả cho offset 5:

```text
isBoundary(5) = false
preceding(5)  = 4
following(5)  = 6
```

Không dùng trực tiếp một offset ngoài phạm vi chuỗi. Các API boundary có hợp đồng riêng cho offset không hợp lệ; code UI nên validate khoảng `0..text.length()` trước.

### Nếu cần cắt theo vị trí end

Khi có một điểm cắt ngẫu nhiên `cut`, hai policy khác nhau:

- **Cắt xuống** để không vượt quá giới hạn đơn vị UTF-16 ban đầu: dùng boundary nhỏ hơn hoặc bằng `cut`.
- **Cắt lên** để lấy trọn cụm có chứa `cut`: dùng boundary lớn hơn hoặc bằng `cut`.

Hai policy ảnh hưởng nội dung output khác nhau. Hãy xác định rõ yêu cầu thay vì tự chọn `following` vì trông “an toàn”.

## 8. BreakIterator và Unicode grapheme cluster: giới hạn cần biết

Tài liệu Java mô tả `BreakIterator.getCharacterInstance` dành cho character boundaries. Trong nhiều trường hợp, ví dụ chữ cái cộng combining marks hay emoji đơn, nó cho kết quả tương ứng điều người dùng mong đợi. Tuy nhiên, **không nên khẳng định mọi JDK từ Java 17 trở lên, mọi locale/provider, đều triển khai trùng khớp phiên bản mới nhất của Unicode Extended Grapheme Cluster**.

Những ví dụ cần kiểm thử riêng:

| Loại | Ví dụ Unicode | Khó khăn |
| --- | --- | --- |
| Chữ + combining marks | `a + U+0306 + U+0301` | Không tách dấu khỏi chữ |
| Surrogate pair | `U+1F600` | Không cắt giữa high/low surrogate |
| Emoji modifier | Thumbs-up + skin tone | Giữ cụm modifier theo chuẩn cần dùng |
| Zero Width Joiner sequence | Woman + ZWJ + laptop | Không tách emoji nghề nghiệp nếu renderer dùng một cụm |
| Regional indicators | Hai ký tự tạo cờ | Quy tắc ghép cặp regional indicators |
| Variation selector | Symbol + VS16 | Không tách selector khỏi ký hiệu |
| CRLF | `\r\n` | Quy tắc ngắt cụm riêng |
| Chữ hệ Indic, Thai, Khmer | Dãy combining/virama | Phụ thuộc Unicode segmentation và shaping |

Ở một số JDK được kiểm tra, `BreakIterator` có thể gộp emoji ZWJ, modifiers, cờ RI và CRLF thành các cụm; nhưng **không thể lấy kết quả đó thay bảo đảm phổ quát** cho tất cả bản Java 17 hoặc Unicode phiên bản khác.

Đối với sản phẩm có yêu cầu phân đoạn emoji hiện đại nghiêm ngặt, hãy xác định **phiên bản Unicode** và hành vi Java runtime thực tế. Có thể cần một thư viện segmentation chuyên dụng được cập nhật đồng bộ với Unicode specification hoặc một test suite chuẩn của Unicode.

### Unicode Text Segmentation không đồng nghĩa “một glyph”

Một *extended grapheme cluster* thường tương ứng với thao tác chỉnh sửa mà người dùng cảm nhận là một ký tự, nhưng:

- Một cluster có thể được vẽ bằng nhiều glyph.
- Nhiều cluster có thể tạo ligature trong shaping.
- Dấu kết hợp có thể được font vẽ chồng lên chữ cơ sở.
- Emoji có thể được renderer hỗ trợ hoặc không hỗ trợ tổ hợp mới.
- Độ rộng của cluster phụ thuộc font, cỡ chữ, script và layout engine.

Vì vậy **đếm cụm không phải giới hạn số pixel**. Nếu UI muốn nhãn nằm trong chiều rộng 120 px, cần đo glyph/text layout và có thể cắt từng boundary theo độ rộng đã đo; BreakIterator chỉ cung cấp **những vị trí có thể cắt**, không tính pixel.

## 9. So sánh với Pattern "\\X" và codePoints

Java `java.util.regex.Pattern` hỗ trợ `\\X` trong regex Java source để match **extended grapheme cluster** theo mô tả Unicode (không phải một chữ cái riêng).

Ví dụ:

```java
import java.util.regex.Pattern;

String decomposed = "a\u0306\u0301";

long matchedClusters = Pattern.compile("\\X")
        .matcher(decomposed)
        .results()
        .count();

System.out.println(matchedClusters);
```

Stdout trong ví dụ:

```text
1
```

Phân biệt các công cụ:

| Cách | Đơn vị xử lý | Khi nên dùng |
| --- | --- | --- |
| `String.length()` | UTF-16 code unit | Giới hạn API/offset dựa trên UTF-16 |
| `String.codePoints()` | Unicode code point | Xử lý mã ký tự, Unicode category |
| `BreakIterator.getCharacterInstance` | Character boundary theo implementation/provider/locale | Duyệt vị trí cắt, tích hợp API localization |
| Regex `\\X` | Extended grapheme cluster theo regex engine/JDK | Tìm đoạn khớp grapheme, đếm theo pattern |
| `Normalizer.normalize` | Chuẩn hóa NFC/NFD/NFKC | Thống nhất biểu diễn Unicode, không phải segmentation |

Regex `\\X` và `BreakIterator` có thể không có **cùng hành vi với mọi Unicode sequence và mọi JDK**. Hai cơ chế sử dụng code path khác nhau, phiên bản dữ liệu Unicode có thể không giống nhau; cần kiểm chứng nếu tính đồng nhất là yêu cầu cứng.

Không thay thế `BreakIterator.getCharacterInstance` bằng `Pattern.compile(".")`: dấu chấm trong regex không định nghĩa một grapheme cluster và có quy tắc về newline, supplementary code points riêng.

## 10. Phân đoạn ký tự có phụ thuộc locale không?

`BreakIterator` nhận `Locale` để chọn quy tắc phân đoạn thích hợp. Một ứng dụng cần biết locale văn bản hoặc locale của người dùng để thiết lập iterator. Tuy nhiên, có những giới hạn:

- Nhiều quy tắc **character boundaries** có tính Unicode chung, không đổi chỉ vì tiếng Việt so với tiếng Anh.
- **Word boundary** và **line break** có thể chịu tác động locale rõ hơn (nhất là ngôn ngữ không dùng dấu cách tách từ).
- Dữ liệu JDK/locale provider có thể khác nhau giữa môi trường.
- Truyền `Locale.getDefault()` ngầm có thể làm behavior phụ thuộc JVM; khi cần tái lập chính xác, truyền locale tường minh.

Không suy rằng `Locale.forLanguageTag("vi-VN")` tự kiểm tra chính tả, tự chuyển “hoà/hòa” theo quy tắc đặt dấu hoặc bỏ dấu thanh. Nó là **cấu hình của segmentation provider**, không phải bộ xử lý ngôn ngữ tiếng Việt hoàn chỉnh.

### BreakIterator có tự normalize Unicode không?

Không nên xem kết quả `BreakIterator` là một lời cam kết sẽ đổi NFC/NFD. API trả **offset**, không thay đổi chuỗi dữ liệu gốc. Hàm `takeClusters` giữ nguyên dãy code unit của phần được lấy.

Nếu một hệ thống muốn lưu NFC để tránh hai chuỗi nhìn giống nhưng code point khác nhau, hãy chuẩn hóa **ở ranh giới dữ liệu** theo chính sách riêng, rồi cập nhật offsets và mappings tương ứng. Đừng normalize sau khi đã lưu offset vì độ dài UTF-16 có thể thay đổi.

## 11. Những vấn đề hiệu năng và thread safety

`BreakIterator` là **đối tượng có trạng thái**: `setText` và các phương thức duyệt thay đổi vị trí hiện tại của iterator. Không chia sẻ một instance mutable cho nhiều request/thread cùng lúc rồi liên tục `setText`.

Một số hướng:

1. **Tạo iterator mới theo từng tác vụ** — dễ hiểu, đúng scope và an toàn về state.
2. **Clone** iterator cấu hình sẵn nếu cần tái sử dụng cấu hình mà không chia sẻ con trỏ duyệt.
3. Nếu buộc dùng chung, phải đồng bộ toàn bộ khối `setText`/duyệt; không chỉ đồng bộ một lần gọi `next`.
4. Với text dài, duyệt trực tiếp và dừng khi đủ số cụm thay vì luôn tạo toàn bộ list.

Độ phức tạp xử lý segmentation còn phụ thuộc text/implementation; không nên đoán chi phí tuyệt đối hoặc giả định một phương thức `next` có cùng thời gian trên mọi chuỗi. Benchmark với dữ liệu thật gồm tiếng Việt có dấu, emoji và text mixed-script.

### Dữ liệu không tin cậy

Khi người dùng gửi text dài, code segmentation nên kiểm soát độ dài input, thời gian xử lý và giới hạn tài nguyên theo nghiệp vụ. Bản thân `BreakIterator` không xác thực nội dung Unicode hợp lệ, không phát hiện mọi ký tự vô hình gây spoofing và không bảo đảm text “an toàn để hiển thị”.

Nếu cần cấm một số Unicode controls trong identifier, hãy kiểm tra theo schema riêng. Không loại tất cả combining marks chỉ để đơn giản hóa segmentation, vì làm vậy mất dấu tiếng Việt.

## 12. Xử lý ký tự điều khiển, khoảng trắng và dấu câu

Một *grapheme cluster* không nhất thiết là một chữ cái có thể in:

- Khoảng trắng có thể là một cụm riêng.
- Dấu chấm/dấu phẩy có thể tạo một cụm riêng.
- Newline hoặc CRLF có quy tắc đặc biệt.
- Ký tự format/zero-width có thể ảnh hưởng phân đoạn mà không có glyph hiển thị.
- Một combining mark đứng lẻ ở đầu văn bản có thể hình thành một cụm dù không có base letter hợp lệ theo nhu cầu ngôn ngữ.

Vì vậy giới hạn `maxClusters = 20` **đếm cả khoảng trắng hoặc dấu câu** nếu chúng là những cụm riêng. Nếu yêu cầu nghiệp vụ là “20 chữ cái” hoặc “20 âm tiết” thì cần thêm bước xác định ký tự nào được tính; `BreakIterator` không tự biết đơn vị nghiệp vụ đó.

Đặc biệt, không nên dùng segmentation để quyết định văn bản hợp lệ khi người dùng nhập tên riêng. Validator có thể cho phép chữ cái, dấu kết hợp, dấu nối, khoảng trắng tùy bối cảnh. Cắt theo cụm chỉ là một phần của UI/validation.

### Dữ liệu với newline

`String` có thể chứa `\n` hoặc `\r\n`. Nếu cắt ở một position gần newline, hãy kiểm tra biên mà segmentation provider trả về; nếu UI cần duy trì nguyên cặp CRLF, có thể thêm test riêng. Không giả định `String.length()` hoặc count code points cho cặp newline cũng bằng grapheme count trong mọi ngữ cảnh.

## 13. Giới hạn theo số cụm khác giới hạn theo byte lưu trữ

Một ô nhập có thể cần:

- Tối đa **100 grapheme cluster** theo trải nghiệm người dùng.
- Tối đa **255 UTF-8 bytes** do giới hạn giao thức.
- Chỉ cho phép một tập Unicode nhất định theo schema.
- Giữ nguyên **NFC** khi lưu.
- Không cho phép một số control character.

Đây là các yêu cầu **độc lập**; một check duy nhất không đủ.

Ví dụ một cluster emoji có thể có nhiều byte UTF-8. Một chữ Việt dạng NFD có nhiều code point nhưng vẫn thường một cluster. Nếu kiểm tra số byte bằng cách `text.getBytes(StandardCharsets.UTF_8).length`, kết quả không phải số grapheme.

Một policy hợp lý cho input:

1. Chọn dạng normalization lưu trữ (nếu có).
2. Quy định **đơn vị độ dài**: grapheme, code point, UTF-16 hay byte.
3. Dùng `BreakIterator` hoặc segmentation phù hợp để kiểm tra grapheme.
4. Nếu có giới hạn byte, kiểm tra byte sau encoding được quy định.
5. Kiểm tra tập ký tự/schema và những control không được phép.
6. Khi hiển thị text dài, dùng text layout để đảm bảo không vượt pixel, và ellipsis theo chính sách rõ ràng.

### Không dùng giới hạn grapheme để phòng mọi vấn đề tài nguyên

Một grapheme cluster có thể chứa nhiều combining marks; chuỗi chỉ một cluster vẫn có thể rất dài theo code point hoặc byte. Nếu nhận dữ liệu không tin cậy, nên đặt **giới hạn thô theo byte/code point** để tránh một cluster quá lớn gây áp lực xử lý, bên cạnh giới hạn số cụm cho UX.

## 14. Kiểm thử đầy đủ với Java và Unicode

Một bộ test hữu ích:

| Trường hợp | Input minh họa | Điều cần xác nhận |
| --- | --- | --- |
| Chuỗi rỗng | `""` | 0 cụm, prefix rỗng |
| ASCII | `ABC` | Các boundaries như dự kiến |
| Tiếng Việt NFC | `"\u1EAF"` | Một cụm ở trường hợp cơ bản |
| Tiếng Việt NFD | `"a\u0306\u0301"` | Không tách dấu breve/acute khỏi a |
| Emoji ngoài BMP | `"\uD83D\uDE00"` | Không cắt giữa surrogate pair |
| Emoji + skin tone | Thumbs-up + modifier | Kiểm tra provider/JDK có gom đúng không |
| Emoji ZWJ | Woman + ZWJ + laptop | Kiểm tra quy tắc ZWJ và version Unicode |
| Cờ regional indicator | Cặp RI Unicode | Kiểm tra quy tắc ghép cặp |
| Variation selector | Symbol + VS16 | Không tách selector khỏi symbol theo chính sách |
| CRLF | `"\r\n"` | Kiểm tra boundary cho cặp newline |
| Combining mark đầu chuỗi | `"\u0301a"` | Không crash, giữ nội dung khi cắt |
| Văn bản mixed-script | Tiếng Việt + Arabic/Hebrew | Segmentation không bị nhầm với bidi reorder |
| Nhiều dấu liên tiếp | `"a\u0301\u0302\u0303"` | Không cắt tùy tiện giữa một cụm |
| Input rất dài | Nhiều đoạn kết hợp | Đánh giá thời gian/bộ nhớ, giới hạn thô |

Nếu cần đảm bảo tương thích với **Unicode GraphemeBreakTest.txt** của một phiên bản cụ thể, hãy dùng test data chính thức để kiểm tra segmentation engine. Không suy rằng vì một vài ví dụ emoji chạy đúng nên mọi quy tắc GB của UAX #29 đều được hỗ trợ.

### Kiểm tra đúng phiên bản runtime

Ứng dụng build bằng JDK 17 nhưng chạy trên JDK khác có thể nhận segmentation data khác. Trong CI:

- Chạy test bằng **runtime version mục tiêu**.
- Ghi nhận JDK vendor/version/provider khi test segmentation quốc tế hóa quan trọng.
- Không khóa cứng kết quả emoji phức hợp qua mọi runtime nếu không có hợp đồng phiên bản Unicode.
- Kiểm tra text preview, caret/select/delete thực tế trong UI; logic backend đúng chưa bảo đảm renderer xử lý mọi tổ hợp đúng.

## 15. Sai lầm thường gặp

| Sai lầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| `String.length()` là số chữ nhìn thấy | Đếm UTF-16 code unit | Chọn đúng đơn vị cần giới hạn |
| `codePoints()` chắc chắn cho số grapheme | Dấu kết hợp có code point riêng | Dùng segmentation theo cluster |
| `substring(0, n)` luôn cắt an toàn | Có thể cắt giữa dấu hoặc surrogate | Lấy boundary từ BreakIterator |
| Normalize NFC rồi cắt từng char | Emoji và nhiều tổ hợp vẫn nhiều code unit | Segmentation vẫn cần thiết |
| Dùng `getWordInstance` để cắt theo chữ | Word breaks khác character breaks | Dùng `getCharacterInstance` |
| Quên gọi `setText` | Iterator chưa phân tích đúng đầu vào | Set text trước khi duyệt |
| Không kiểm tra `DONE` | Có thể dùng offset -1 và lỗi substring | Kiểm tra sentinel đúng |
| Coi `end` là inclusive | substring có end-exclusive | Dùng `substring(start,end)` |
| Xem offsets là code-point indexes | BreakIterator trả UTF-16 positions | Không trộn đơn vị chỉ số |
| Gọi `preceding` như floor inclusive | Nó tìm boundary **strictly before** | Kiểm tra `isBoundary` trước |
| Chia sẻ một iterator giữa threads | Iterator giữ mutable state | Tạo instance riêng/clone |
| Giới hạn grapheme cũng giới hạn byte | Một cluster có thể dài nhiều byte | Đặt byte limit riêng |
| Cắt theo cụm là đo độ rộng UI | Một cluster có thể nhiều glyph | Dùng renderer/text layout |
| Mọi JDK 17 đều giống Unicode mới nhất | Provider/Unicode version có thể khác | Test runtime mục tiêu |
| Cho rằng segmentation sửa chính tả | Nó chỉ tìm ranh giới text | Validation ngôn ngữ riêng |
| Lọc hết combining marks để dễ cắt | Mất dấu tiếng Việt | Giữ dữ liệu, cắt theo biên |

## 16. Bài tập thực hành

**Bài 1 — ba đơn vị.** Tạo `"\u1EAF"` và `"a\u0306\u0301"`. Đếm `length()`, `codePointCount` và số cụm bằng `BreakIterator.getCharacterInstance`. Giải thích vì sao hình chữ tương đương nhưng số code unit khác.

**Bài 2 — lỗi substring.** Cho `"A" + "a\u0306\u0301" + "B"`. Vì sao `substring(0,2)` làm mất hai dấu? Viết hàm lấy hai cụm đầu.

**Bài 3 — emoji ngoài BMP.** Dùng `"\uD83D\uDE00"`. Chỉ ra index nằm giữa surrogate pair. So sánh kết quả cắt theo code unit với cắt theo BreakIterator.

**Bài 4 — isBoundary.** Với chuỗi demo có emoji ở khoảng `[4,6)`, dự đoán `isBoundary(5)`, `preceding(5)` và `following(5)`. Viết helper snap điểm cắt xuống boundary gần nhất không vượt giới hạn.

**Bài 5 — ellipsis.** Viết hàm truncate có budget 8 cụm **bao gồm** một dấu `…` khi text bị cắt. Trường hợp không phải cắt thì không thêm ellipsis. Test input rỗng và budget 0.

**Bài 6 — regex X.** Dùng `Pattern.compile("\\X")` để đếm grapheme rồi so sánh với `BreakIterator.getCharacterInstance` trên NFC/NFD và một emoji ZWJ. Nếu JDK cho kết quả khác thì phần nào của hệ thống cần cố định policy?

**Bài 7 — giới hạn lưu trữ.** Một username cho phép tối đa 20 cụm nhưng database giới hạn 64 UTF-8 bytes. Vì sao một check grapheme không đủ? Đề xuất thứ tự validation và thông báo lỗi cho người dùng.

**Bài 8 — đa ngôn ngữ.** Với văn bản gồm chữ Latin, tiếng Việt có dấu và Arabic, thử phân đoạn bằng `BreakIterator`. Tại sao kết quả này không thay thế `java.text.Bidi` trong việc hiển thị RTL?

**Bài 9 — phụ thuộc JDK.** Thiết kế test gồm modifier, ZWJ, cờ RI và CRLF, chạy cùng test trên hai phiên bản Java. Ghi lại count và offsets. Thảo luận cách xử lý khi đầu ra khác nhau.

## 17. Kết luận

`BreakIterator.getCharacterInstance(Locale)` là API Java Core để duyệt **các ranh giới ký tự** của văn bản, hữu ích khi muốn cắt text không tách dấu kết hợp khỏi chữ cơ sở hoặc cắt đôi surrogate pair. Khi duyệt qua `first()/next()`, mỗi đoạn được lấy bằng `substring(start,end)` với chỉ số UTF-16 end-exclusive; không được hiểu số cụm là `String.length()`.

Phân đoạn text **khác** chuẩn hóa Unicode, kiểm tra chính tả, đo bề rộng glyph và hiển thị hai chiều. Với UI hiện đại có emoji phức hợp, cần kiểm tra khả năng của đúng JDK/provider và phiên bản Unicode; nếu cần tuân thủ hoàn toàn một profile Extended Grapheme Cluster nhất định, hãy chọn segmentation engine/test suite phù hợp.

**Nguyên tắc cốt lõi:** *Cắt văn bản theo boundary của cụm, không cắt bằng một chỉ số char tùy ý; luôn hiểu đơn vị offset và kiểm thử các chuỗi Unicode đa code point.*

### Tài liệu tham khảo

- [`BreakIterator` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html)
- [`String` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Pattern` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Standard Annex #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
