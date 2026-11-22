# Cắt theo cụm ký tự bằng BreakIterator trong Java

Khi cần giới hạn một dòng văn bản theo **số ký tự mà người đọc cảm nhận** — ví dụ cắt nhãn hiển thị, lấy một phần tên người dùng, di chuyển con trỏ hoặc chọn đoạn chữ — chỉ số của `String.substring()` có thể khiến ta cắt sai vị trí. Trong Java, `String` được đánh chỉ số bằng **đơn vị mã UTF-16**; một “ký tự” được người dùng nhận thấy có thể bao gồm **nhiều đơn vị mã** và **nhiều Unicode code point**.

`java.text.BreakIterator.getCharacterInstance(...)` cung cấp cách tìm **ranh giới cụm ký tự** (*character/grapheme boundaries*) cho văn bản. Ta lấy các chỉ số ranh giới mà iterator trả về, rồi dùng `substring(start, end)` tại đúng các vị trí đó. Cách này giúp tránh cắt đôi nhiều tổ hợp chữ có dấu và cặp surrogate; hành vi cụ thể, nhất là với emoji phức tạp, còn phụ thuộc phiên bản JDK và bộ quy tắc Unicode mà nó triển khai.

## 1. Vì sao `substring` thông thường có thể cắt sai?

Xét chuỗi được tạo từ:

- Chữ `A`: một UTF-16 code unit, một code point.
- Dấu sắc kết hợp `U+0301`: thêm một code point/UTF-16 code unit; cùng `A` tạo thành cụm mà mắt thường nhìn thấy như `Á`.
- Emoji 😀 (`U+1F600`): một code point nhưng **hai** UTF-16 code units (cặp surrogate).
- Chữ `B`: một code unit, một code point.

Trong mã Java:

```java
String text = "A\u0301" + new String(Character.toChars(0x1F600)) + "B";
```

Cách chia theo mã UTF-16:

```text
UTF-16 index:  0     1         2       3       4       5
               |  A  | U+0301  | high  | low   |   B   |
               |--- cụm 1 ----|--- cụm 2 -----| cụm 3 |
Ranh giới:     0               2               4       5
```

Giá trị cần phân biệt:

| Phép đo | Kết quả | Đang đếm gì? |
|---|---:|---|
| `text.length()` | 5 | UTF-16 code units |
| `text.codePointCount(0, text.length())` | 4 | Unicode code points, với surrogate pair hợp lệ đếm một |
| Số cụm ký tự theo character `BreakIterator` (ví dụ này) | 3 | `A` + dấu sắc, emoji 😀, `B` |

Nếu gọi `text.substring(0, 1)`, kết quả chỉ gồm `A`, **mất dấu kết hợp**. Nếu gọi `text.substring(0, 3)`, kết quả sẽ chứa `A`, dấu kết hợp và **nửa đầu của surrogate pair**, tạo một chuỗi UTF-16 không well-formed. Dùng `offsetByCodePoints` giúp giữ ranh giới *code point*, nhưng vẫn có thể cắt giữa chữ cái và dấu kết hợp. Vì thế, bài toán “lấy N ký tự mà người dùng nhìn thấy” cần một phép chia cấp cao hơn code unit/code point.

### Grapheme cluster có đồng nghĩa một glyph không?

Không hoàn toàn. *Grapheme cluster* là **đơn vị phân đoạn văn bản theo quy tắc Unicode**, gần với khái niệm “một ký tự” của người dùng. Một cụm có thể chứa chữ cái cộng dấu, một emoji có bộ điều chỉnh màu da, cờ ghép từ regional indicators hoặc emoji nối bằng ZWJ. Tuy nhiên cách font hiển thị thành một hay nhiều hình (*glyph*) còn phụ thuộc môi trường render. Vì vậy, ranh giới grapheme không phải phép đo chiều rộng hiển thị hay số glyph chính xác.

## 2. `BreakIterator` làm gì?

`BreakIterator` trong package `java.text` là iterator **có trạng thái**, định vị các **ranh giới** trong văn bản. Nó không trực tiếp trả về `List<String>`. Các giá trị mà nó trả về là **offset UTF-16** thích hợp để truyền vào `String.substring(...)`.

Khởi tạo cho ranh giới kiểu “ký tự”:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
iterator.setText("A\u0301B");
```

- `getCharacterInstance(locale)`: chọn **character boundaries**; đừng nhầm với `getWordInstance` (tách từ), `getLineInstance` (khả năng xuống dòng), `getSentenceInstance` (câu).
- `Locale.ROOT` giúp ví dụ không phụ thuộc default locale của môi trường. Với ứng dụng có ngôn ngữ cụ thể, có thể truyền locale phù hợp, chẳng hạn `Locale.forLanguageTag("vi-VN")`. Các provider, phiên bản JDK và dữ liệu Unicode vẫn có thể ảnh hưởng kết quả.
- `setText(text)`: đặt văn bản đang duyệt và đưa iterator về ranh giới đầu. Tạo mới iterator hoặc gọi lại `setText` khi xử lý một chuỗi mới.

Các thao tác quan trọng:

| Phương thức | Tác dụng |
|---|---|
| `first()` | Trả về ranh giới đầu, thường là offset `0` với `String`. |
| `next()` | Trả về ranh giới kế tiếp hoặc `BreakIterator.DONE` nếu hết. |
| `last()` | Trả về ranh giới cuối, bằng `text.length()` với `String` đã đặt. |
| `previous()` | Di chuyển về ranh giới phía trước; trả `DONE` nếu không còn. |
| `following(i)` | Tìm **ranh giới đầu tiên lớn hơn** offset `i`, không phải lớn hơn hoặc bằng. |
| `preceding(i)` | Tìm **ranh giới cuối cùng nhỏ hơn** offset `i`. |
| `isBoundary(i)` | Kiểm tra offset `i` có đúng ranh giới được iterator chấp nhận hay không. |
| `current()` | Lấy offset ranh giới hiện tại của iterator. |
| `BreakIterator.DONE` | Giá trị đánh dấu hết, **không** phải vị trí dùng làm chỉ số `substring`. |

Chú ý `following`, `preceding` và `isBoundary` có thể thay đổi vị trí của iterator. Khi duyệt toàn bộ từ đầu, hãy gọi `first()` rồi `next()` theo thứ tự; đừng thực hiện kiểm tra ranh giới xen giữa mà quên trạng thái đã thay đổi.

## 3. Duyệt từng cụm ký tự

Mẫu vòng lặp thường dùng:

```java
BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(text);

int start = it.first();
for (int end = it.next(); end != BreakIterator.DONE; end = it.next()) {
    String cluster = text.substring(start, end);
    // Dùng cluster để hiển thị, đếm hoặc xử lý
    start = end;
}
```

Đây là **đoạn mã minh họa**, giả định `text` đã được khai báo. Thứ tự là:

1. `first()` trả ranh giới đầu tiên và gán vào `start`.
2. `next()` trả ranh giới kế tiếp và gán vào `end`.
3. `substring(start, end)` lấy một đoạn giữa **hai ranh giới liên tiếp**; `start` tính vào, `end` không tính vào.
4. Dời `start = end` để chuẩn bị cụm tiếp theo.
5. Dừng khi `next()` trả `DONE`; không gọi `substring` với `DONE`.

Duyệt như vậy giữ lại mọi khoảng trắng và dấu câu thành các đoạn theo quy tắc character boundary; nó **không loại bỏ** khoảng trắng hay tách “từ”. Với chuỗi rỗng, iterator có một ranh giới `0` và không có đoạn nội dung nào để duyệt.

## 4. Ví dụ hoàn chỉnh: tách và cắt theo chỉ số cụm ký tự

Chương trình sau đặt toàn bộ ranh giới vào danh sách `offsets`. Nhờ thế có thể:

- Tách chuỗi thành danh sách cụm bằng `splitClusters(text)`.
- Lấy đoạn từ cụm `from` (**bao gồm**) đến cụm `to` (**không bao gồm**) bằng `sliceClusters(text, from, to)`.
- Lấy `N` cụm đầu bằng `sliceClusters(text, 0, N)`.

Lưu tệp **`GraphemeCutDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class GraphemeCutDemo {
    // Kết quả gồm cả hai ranh giới đầu và cuối, theo chỉ số UTF-16.
    public static List<Integer> boundaries(String text) {
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(text);

        List<Integer> offsets = new ArrayList<>();
        for (int i = iterator.first();
                i != BreakIterator.DONE;
                i = iterator.next()) {
            offsets.add(i);
        }
        return offsets;
    }

    public static List<String> splitClusters(String text) {
        List<Integer> offsets = boundaries(text);
        List<String> result = new ArrayList<>();

        for (int i = 0; i + 1 < offsets.size(); i++) {
            result.add(text.substring(offsets.get(i), offsets.get(i + 1)));
        }
        return result;
    }

    // Cắt khoảng [from, to), đơn vị là cụm ký tự.
    public static String sliceClusters(String text, int from, int to) {
        List<Integer> offsets = boundaries(text);
        int clusterCount = offsets.size() - 1;

        if (from < 0 || to < from || to > clusterCount) {
            throw new IndexOutOfBoundsException(
                    "Invalid cluster range: [" + from + ", " + to + ")");
        }

        return text.substring(offsets.get(from), offsets.get(to));
    }

    public static void main(String[] args) {
        String text = "A\u0301"
                + new String(Character.toChars(0x1F600))
                + "B";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Offsets: " + boundaries(text));
        System.out.println("Clusters: " + splitClusters(text).size());
        System.out.println("Lengths: "
                + splitClusters(text).stream().map(String::length).toList());

        System.out.println("First: " + sliceClusters(text, 0, 1).length());
        System.out.println("First 2: " + sliceClusters(text, 0, 2).length());
        System.out.println("Last 2: " + sliceClusters(text, 1, 3).length());
        System.out.println("Empty: " + sliceClusters(text, 2, 2).length());

        BreakIterator probe =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        probe.setText(text);

        System.out.println("Boundary at 1: " + probe.isBoundary(1));
        System.out.println("Boundary at 3: " + probe.isBoundary(3));
        System.out.println("Following 2: " + probe.following(2));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 GraphemeCutDemo.java
java GraphemeCutDemo
```

Đầu ra với phân đoạn cơ bản trong ví dụ:

```text
UTF-16 units: 5
Code points: 4
Offsets: [0, 2, 4, 5]
Clusters: 3
Lengths: [2, 2, 1]
First: 2
First 2: 4
Last 2: 3
Empty: 0
Boundary at 1: false
Boundary at 3: false
Following 2: 4
```

Giải thích:

- Danh sách ranh giới `[0, 2, 4, 5]` tạo ra **3** đoạn có độ dài UTF-16 `[2, 2, 1]`.
- `sliceClusters(text, 0, 1)` lấy **cả `A` và dấu kết hợp**, nên có độ dài UTF-16 là 2.
- `sliceClusters(text, 0, 2)` còn gồm **toàn bộ cặp surrogate của emoji**, nên có độ dài 4.
- `sliceClusters(text, 1, 3)` trả emoji cùng `B`, tổng cộng 3 UTF-16 code units.
- `sliceClusters(text, 2, 2)` trả chuỗi rỗng vì đoạn cắt nửa mở `[2, 2)` không có cụm nào.
- Offset `1` rơi vào giữa chữ `A` và dấu kết hợp; offset `3` rơi vào giữa surrogate pair: cả hai không phải ranh giới.
- `following(2)` trả `4` vì phải tìm ranh giới **lớn hơn** `2`.

Dữ liệu mẫu được dựng từ escape Unicode và `Character.toChars` để kết quả đếm không phụ thuộc việc terminal có font hỗ trợ emoji hay không. Đây là chương trình hoàn chỉnh có thể biên dịch; các đoạn mã ngắn ở các mục khác nhằm minh họa cách dùng API.

### Vì sao cần hai danh sách: ranh giới và cụm?

`boundaries` chứa **offset**, có `m + 1` phần tử cho `m` cụm. Dùng hai offset liên tiếp làm giới hạn `substring` sẽ không mất phần nào của chuỗi. Danh sách `splitClusters` có đúng `m` đoạn, nối tất cả các đoạn theo thứ tự sẽ tạo lại nội dung ban đầu:

```java
String original = "A\u0301B";
String reconstructed = String.join("", splitClusters(original));
System.out.println(original.equals(reconstructed)); // true
```

Lưu ý đoạn cuối là **minh họa cách dùng**, giả định gọi trong cùng lớp hoặc truy cập `GraphemeCutDemo.splitClusters(...)` từ lớp khác.

## 5. Cắt N cụm đầu và xử lý chỉ số không hợp lệ

Gọi:

```java
String firstTwo = sliceClusters(text, 0, 2);
```

nếu `text` có ít nhất hai cụm. Hàm trong ví dụ dùng **quy tắc chặt**:

- `from == to` hợp lệ nếu nằm trong khoảng `0` đến số cụm; kết quả là chuỗi rỗng.
- `from < 0`, `to < from` hoặc `to` lớn hơn số cụm đều báo `IndexOutOfBoundsException`.
- `sliceClusters("", 0, 0)` hợp lệ và trả `""`.
- `sliceClusters("", 0, 1)` không hợp lệ vì chuỗi rỗng có 0 cụm.

Với giao diện giới hạn “tối đa N cụm” (ví dụ preview văn bản), có thể chọn chính sách **cắt tới hết nếu N vượt quá số cụm**:

```java
static String takeUpToClusters(String text, int maxClusters) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("maxClusters must be >= 0");
    }

    BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
    it.setText(text);

    int end = it.first();
    for (int n = 0; n < maxClusters; n++) {
        int next = it.next();
        if (next == BreakIterator.DONE) {
            break;
        }
        end = next;
    }
    return text.substring(0, end);
}
```

Đây là **phương thức bổ sung** có thể đặt vào `GraphemeCutDemo`, không phải chương trình chạy độc lập. Nó chỉ giữ offset kết thúc và có chi phí bộ nhớ bổ sung rất nhỏ; phù hợp khi chỉ cần lấy prefix, không cần lưu mọi ranh giới. Nếu `maxClusters` bằng 0, kết quả là chuỗi rỗng; nếu vượt số cụm, kết quả là toàn bộ chuỗi.

Hai chính sách đều hợp lý, nhưng phải được đặt tên và ghi rõ: **`sliceClusters` kiểm tra range**, còn **`takeUpToClusters` giới hạn tối đa**.

## 6. JDK 17 và JDK 20+: lưu ý emoji phức tạp

Đây là giới hạn quan trọng nhất khi dùng `BreakIterator`.

Trong **JDK 20**, triển khai character boundary mặc định được cập nhật để tuân theo quy tắc **Unicode Extended Grapheme Cluster** (UAX #29). Trước thay đổi đó, đặc biệt với **emoji ZWJ** và **cờ ghép từ hai regional indicators**, một số bản JDK cũ có thể trả các ranh giới khiến tổ hợp hiển thị bị tách ra.

Ví dụ tổ hợp:

```text
🇺🇸 👨‍👩‍👧‍👦
```

- Trên triển khai đã hỗ trợ Extended Grapheme Cluster theo quy tắc hiện hành, hai tổ hợp trên được tách thành **hai cụm** (nếu viết liền nhau, không có dấu cách).
- Trên một số JDK trước 20, character `BreakIterator` có thể chia thành nhiều đoạn nhỏ hơn, thậm chí tách các thành phần nối bằng **ZWJ (U+200D)** hoặc các ký hiệu regional indicator.

Do đó, **không dùng output số cụm emoji phức tạp từ một bản JDK làm hợp đồng chung cho mọi bản**. Cần kiểm tra phiên bản JVM, provider, dữ liệu Unicode và nhu cầu của hệ thống. Nếu ứng dụng yêu cầu phân đoạn Unicode nghiêm ngặt, nhất quán giữa nhiều phiên bản JDK, hãy chọn và kiểm thử một bộ triển khai rõ ràng (chẳng hạn ICU4J nếu phù hợp) cùng phiên bản dữ liệu Unicode được quản lý.

Bài demo ở mục 4 cố ý dùng tổ hợp **chữ + dấu kết hợp** và một **code point emoji bổ sung** thay vì emoji ZWJ phức tạp để trình bày nguyên tắc ranh giới và có kết quả dễ kiểm tra trên các JDK thông dụng.

Điều này cũng cho thấy “cụm ký tự” là kết quả của **quy tắc phân đoạn**, không phải chỉ việc đếm code point hoặc cắt mỗi `char`.

## 7. Dùng `following`, `preceding` và `isBoundary` khi có offset con trỏ

Một ứng dụng soạn thảo có thể đang lưu vị trí con trỏ dưới dạng **UTF-16 offset**. Trước khi cắt, di chuyển hoặc xóa phần văn bản, cần tránh để offset nằm trong một cụm:

```java
BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(text);

boolean valid = it.isBoundary(cursorUtf16Offset);
int nextBoundary = it.following(cursorUtf16Offset);
int previousBoundary = it.preceding(cursorUtf16Offset);
```

Đoạn trên minh họa API, với `text` và `cursorUtf16Offset` đã được khai báo. Cần lưu ý:

- `isBoundary(i)` chỉ nhận offset trong miền của văn bản; offset ngoài miền có thể ném `IllegalArgumentException`.
- `following(i)` là ranh giới **sau** `i`, kể cả khi `i` vốn đã là ranh giới. Không dùng nó nếu muốn giữ nguyên một con trỏ đã đúng ranh giới.
- `preceding(i)` là ranh giới **trước** `i`, kể cả khi `i` vốn đã là ranh giới.
- `following(text.length())` hoặc `preceding(0)` trả `BreakIterator.DONE`. Phải kiểm tra `DONE` trước khi biến kết quả thành chỉ số `substring`.
- Những lệnh tìm kiếm ranh giới có thể thay đổi trạng thái iterator; không giả định sau `isBoundary` thì `current()` vẫn giữ nguyên vị trí cũ.

Trong giao diện, việc “đẩy con trỏ về ranh giới bên trái hay bên phải” là quyết định trải nghiệm người dùng, không phải một quy tắc cố định của API. Tùy thao tác và hướng kéo, chọn `preceding`, `following` hoặc giữ nguyên `i` khi `isBoundary(i)` là `true`.

## 8. Locale, Unicode normalization và tính đúng của đầu vào

**Locale:** `BreakIterator.getCharacterInstance(locale)` nhận `Locale` để chọn dịch vụ phân đoạn. Điều này **không biến chuỗi đầu vào thành ngôn ngữ đó** và không dịch nội dung. `Locale.ROOT` thuận tiện cho ví dụ; trong ứng dụng quốc tế hóa, dùng locale của văn bản và kiểm thử các script thực tế.

**Unicode normalization:** `BreakIterator` tìm ranh giới, **không chuẩn hóa** chuỗi. Hai biểu diễn `"\u00C1"` (một code point Á) và `"A\u0301"` (A + dấu sắc) có thể nhìn giống nhau nhưng khác dãy code point, độ dài UTF-16 và kết quả `equals()`. Cả hai thường là một cụm khi phân đoạn, nhưng sau khi `substring` chúng vẫn giữ nguyên các đơn vị mã gốc. Nếu ứng dụng cần so sánh dạng chuẩn, cân nhắc `java.text.Normalizer` với chính sách riêng; **đừng âm thầm chuẩn hóa chỉ để thực hiện thao tác cắt**.

**UTF-16 không well-formed:** `String` Java có thể chứa high/low surrogate không ghép cặp. Nếu đầu vào bị lỗi, đừng suy luận rằng tìm được vài boundary nghĩa là dữ liệu Unicode đã hợp lệ. Cần một bước xác thực riêng khi dữ liệu sẽ được mã hóa hoặc trao đổi với hệ thống yêu cầu Unicode scalar values.

**Không bảo đảm hiển thị đẹp:** Giữ ranh giới grapheme vẫn không đảm bảo dòng văn bản vừa kích thước pixel, ký tự có font hỗ trợ, hoặc dòng không vượt chiều rộng. Đo chiều rộng cần công cụ layout/font; ngắt dòng dùng thuật toán tương ứng, không dùng `getCharacterInstance` thay thế đo chiều rộng.

## 9. Hiệu năng và quản lý iterator

- **Chọn đúng nhu cầu:** nếu chỉ lấy vài cụm đầu, thuật toán dùng một iterator và giữ `end` (mục 5) tránh cấp phát danh sách tất cả boundaries. Nếu cần truy vấn nhiều đoạn trên cùng một chuỗi bất biến, tính và tái sử dụng danh sách boundaries có thể tiết kiệm việc phân đoạn lại.
- **Bộ nhớ:** `splitClusters` tạo danh sách và các chuỗi đoạn; `boundaries` tạo danh sách offset theo số cụm. `takeUpToClusters` chỉ giữ một vài biến, ngoài đối tượng iterator.
- **Trạng thái:** một `BreakIterator` có vị trí duyệt và văn bản đang xét; không chia sẻ cùng một instance đang bị thay đổi giữa các thao tác hoặc luồng mà không đồng bộ. Dùng instance riêng cho thao tác độc lập.
- **Chỉ số UTF-16:** dù API tìm ranh giới theo đơn vị gần với ký tự của người dùng, **giá trị trả về vẫn là UTF-16 offset**. Đừng đem số thứ tự cụm dùng trực tiếp làm đối số của `substring`.
- **Chuỗi thay đổi:** nếu văn bản đã sửa, danh sách offset từ lần phân đoạn cũ không còn chắc chắn đúng. Tính lại boundaries sau khi cập nhật chuỗi. `String` bản thân bất biến nhưng biến `text` có thể tham chiếu tới chuỗi khác.
- **Test Unicode:** chuẩn bị ca kiểm thử bao gồm chữ có dấu kết hợp, ký tự ngoài BMP, emoji ZWJ, cờ, một chuỗi rỗng, ngắt dòng và script trong tập người dùng thực tế. Khóa phiên bản thư viện/JDK nếu cần kết quả phân đoạn tái lập.

## 10. Lỗi thường gặp

| Sai lầm | Vì sao có vấn đề | Cách làm đúng |
|---|---|---|
| `substring(0, n)` để lấy `n` ký tự hiển thị | `n` được hiểu là UTF-16 offset | Tìm boundary thứ `n` rồi mới gọi `substring(0, boundary)` |
| Dùng `codePointCount` thay số cụm | Một cụm có thể có nhiều code point | Duyệt character `BreakIterator` |
| Gọi `substring(start, BreakIterator.DONE)` | `DONE` không phải offset hợp lệ | Dừng duyệt trước khi gọi `substring` |
| Gọi `following(i)` để giữ nguyên `i` khi đã đúng boundary | `following` tìm **lớn hơn** `i` | Kiểm tra `isBoundary(i)` trước hoặc áp dụng chính sách rõ ràng |
| Tách bằng `getWordInstance()` | Đang chia theo từ, không phải cụm ký tự | Dùng `getCharacterInstance()` |
| Mặc định emoji ZWJ luôn là một cụm trên JDK 17 | Các quy tắc được cập nhật đáng kể từ JDK 20 | Kiểm tra JDK và phiên bản quy tắc phân đoạn |
| Coi grapheme là độ rộng một ký tự monospace | Rendering và grapheme segmentation khác nhau | Dùng API đo layout khi cần chiều rộng |
| Tái sử dụng iterator khi đã đổi nội dung văn bản | Ranh giới thuộc chuỗi đã đặt bằng `setText` | Gọi lại `setText` hoặc tạo instance mới |
| Nghĩ phân đoạn đồng nghĩa chuẩn hóa Unicode | BreakIterator chỉ tính ranh giới | Xử lý normalization riêng nếu nghiệp vụ yêu cầu |

## 11. Bài tập tự kiểm tra

1. Với `String s = "A\u0301B";`, `s.length()` và số cụm theo `getCharacterInstance` trong ví dụ là bao nhiêu?
2. Nếu danh sách boundaries là `[0, 2, 4, 5]`, `substring(2, 4)` lấy cụm nào? Vì sao `substring(2, 3)` có thể gây vấn đề?
3. Trong hàm `sliceClusters(text, from, to)`, vì sao phải chấp nhận `from == to` nhưng từ chối `to > clusterCount`?
4. Vì sao mã cắt theo code point vẫn có thể tách `A` và dấu kết hợp `U+0301`?
5. Bạn nên kiểm thử gì trước khi dùng character `BreakIterator` trên JDK 17 để cắt emoji gia đình nối bằng ZWJ?

**Gợi ý đáp án:** (1) `length() == 3` và có 2 cụm (`A` + dấu, `B`). (2) `substring(2, 4)` lấy emoji ngoài BMP; `substring(2, 3)` chỉ giữ high surrogate, làm hỏng cặp. (3) Đoạn rỗng là hợp lệ; vượt ngoài số cụm thì không có boundary đích để cắt. (4) Code point khác grapheme cluster. (5) Kiểm thử ranh giới thực tế trên JDK đang triển khai; nếu yêu cầu extended grapheme cluster, cần bản triển khai phù hợp như JDK 20+ hoặc giải pháp khác được kiểm chứng.

## 12. Tài liệu tham khảo

- [Oracle Java SE 17: `java.text.BreakIterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html) — contract `first`, `next`, `following`, `preceding`, `isBoundary` và mô tả character boundary.
- [Oracle JDK 20 Release Notes: Grapheme Support in BreakIterator (JDK-8291660)](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html) — thay đổi để hỗ trợ Extended Grapheme Cluster và ví dụ cờ/emoji ZWJ.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/) — nguyên tắc phân đoạn và ranh giới grapheme clusters.

**Ghi nhớ:** `String` đánh chỉ số bằng UTF-16; `codePoints()` xử lý code point; `BreakIterator.getCharacterInstance(...)` tìm ranh giới cụm ký tự theo quy tắc của bản triển khai. Để cắt an toàn theo các cụm, hãy **tìm hai offset boundary → gọi `substring(start, end)`**, và kiểm tra hành vi emoji phức tạp theo phiên bản JDK thực tế.
