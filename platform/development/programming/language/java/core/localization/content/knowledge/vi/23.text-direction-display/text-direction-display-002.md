# java.text.Bidi và hướng cơ sở trong Java

## Mục tiêu bài học

Một chuỗi Java có thể chứa đồng thời chữ viết **trái sang phải** (*left-to-right*, LTR), như tiếng Việt và tiếng Anh, với chữ viết **phải sang trái** (*right-to-left*, RTL), như tiếng Hebrew hoặc Arabic. Các con số thường có trình tự đọc trái sang phải ngay cả khi nằm trong câu RTL; dấu ngoặc, dấu chấm, dấu hai chấm và khoảng trắng không tự mang một hướng mạnh độc lập. Do đó, **thứ tự ký tự trong bộ nhớ** và **thứ tự nhìn thấy trên màn hình** không phải lúc nào cũng trùng nhau.

`java.text.Bidi` là lớp Java hỗ trợ phân tích thuật toán hai chiều Unicode (*Unicode Bidirectional Algorithm*, UBA). Lớp này xác định **hướng cơ sở của đoạn văn**, **embedding level** và **các đoạn chạy có cùng level** (*directional runs*), tạo cơ sở để hệ thống hiển thị sắp xếp văn bản hỗn hợp cho người đọc.

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa thứ tự logic của `String` và thứ tự hiển thị hai chiều.
- Phân biệt hướng cơ sở (*base direction*), hướng mạnh/yếu/trung tính của ký tự và embedding level.
- Sử dụng bốn lựa chọn `DIRECTION_LEFT_TO_RIGHT`, `DIRECTION_RIGHT_TO_LEFT`, `DIRECTION_DEFAULT_LEFT_TO_RIGHT` và `DIRECTION_DEFAULT_RIGHT_TO_LEFT`.
- Đọc các kết quả `getBaseLevel()`, `baseIsLeftToRight()`, `getRunCount()`, `getRunStart()`, `getRunLimit()` và `getRunLevel()`.
- Hiểu vì sao `isMixed()` không đơn thuần có nghĩa “chuỗi chứa hai bảng chữ khác nhau”.
- Biết khi nào dùng `createLineBidi(...)`, `requiresBidi(...)` và `reorderVisually(...)`, và giới hạn của chúng.
- Tránh đảo chuỗi bằng `StringBuilder.reverse()` hoặc tự đổi thứ tự các ký tự RTL.
- Xử lý các tình huống thực tế: nhãn Arabic/Hebrew xen số, URL, mã sản phẩm, dấu câu, văn bản người dùng nhập, Unicode bidi control và kiểm thử giao diện.
- Phân biệt **bidi analysis** với **glyph shaping**, lựa chọn font, layout của GUI và thuộc tính định hướng của UI.

Bài này nằm trong nhóm **Chiều chữ và hiển thị**. Mục tiêu là hiểu và sử dụng `Bidi` đúng trách nhiệm, không tự xây lại toàn bộ bộ máy vẽ chữ Unicode.

## 1. Vì sao một chuỗi cần thuật toán hai chiều?

Xét văn bản minh họa ở thứ tự logic:

```text
ABC שלום XYZ
```

Trong đó `שלום` là chuỗi chữ Hebrew đọc theo RTL. Thứ tự logic trong `String` vẫn là:

```text
A B C [space] ש ל ו ם [space] X Y Z
```

Các ký tự được lưu theo **thứ tự nội dung**; Java không tự đổi vị trí các chữ Hebrew trong `String` chỉ vì chúng thuộc bảng chữ RTL. Khi hệ thống vẽ, nó cần xử lý hướng của từng run để văn bản hiển thị tự nhiên.

Một số chi tiết khiến “đảo ngược toàn bộ chuỗi” là sai:

- Chữ Latin `ABC` vẫn được đọc LTR.
- Chữ Hebrew được trình bày RTL.
- Số `2026` có thể giữ trình tự đọc số khi nằm trong câu RTL.
- Dấu ngoặc, hai chấm và khoảng trắng phụ thuộc ngữ cảnh; chúng không nhất thiết nằm đúng vị trí nếu chỉ đảo mảng ký tự.
- Một run RTL có thể chứa sub-run LTR ở level sâu hơn.
- Ký tự kết hợp và emoji có thể gồm nhiều code point; đảo từng `char` có thể làm vỡ grapheme hoặc cặp surrogate.

**Bidi không thay thứ tự lưu trữ của `String`**. Nó cung cấp thông tin để hệ thống layout quyết định cách trình bày các phần văn bản theo quy tắc Unicode.

## 2. Ba khái niệm nền tảng: hướng ký tự, hướng cơ sở và level

### 2.1. Hướng của ký tự

Thuật toán bidi sử dụng thuộc tính hướng Unicode (*Bidi_Class*) của từng code point. Một số nhóm nổi bật:

| Nhóm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `L` | Strong left-to-right | Chữ Latin trong tiếng Việt, tiếng Anh |
| `R` | Strong right-to-left | Phần lớn chữ Hebrew |
| `AL` | Arabic right-to-left | Nhiều chữ Arabic |
| `EN` | European number | Chữ số `0–9` |
| `AN` | Arabic number | Một số chữ số Arabic-Indic |
| `WS` | Whitespace | Khoảng trắng |
| `ON` và các nhóm trung tính khác | Dấu/ký hiệu tùy ngữ cảnh | Một số dấu ngoặc, dấu câu |
| `NSM` | Nonspacing mark | Nhiều dấu kết hợp Unicode |

Các ký tự `L`, `R` hoặc `AL` gọi là **strong directional characters**. Nhiều dấu câu, chữ số và khoảng trắng là **weak** hoặc **neutral**: cách xử lý chúng phụ thuộc vào các ký tự gần đó và hướng đoạn văn.

Do đó, nhìn vào chữ số đầu chuỗi không đủ để xác định “đoạn văn này chắc chắn LTR”. Khi dùng hướng tự động, việc lựa chọn thường dựa trên **ký tự mạnh đầu tiên**, không phải ký tự đầu tiên bất kể loại.

### 2.2. Hướng cơ sở (base direction)

**Hướng cơ sở của đoạn văn** xác định hướng nền để giải quyết những phần không có hướng mạnh rõ ràng, đặc biệt là dấu câu, khoảng trắng và các tổ hợp hỗn hợp. Có hai hướng nền chính:

- **LTR:** base level bằng `0`, một level chẵn.
- **RTL:** base level bằng `1`, một level lẻ.

Base direction không có nghĩa mọi run trong đoạn đều chạy theo hướng đó. Một câu RTL vẫn có thể chứa những run LTR; tương tự, một câu tiếng Anh có thể chứa tên riêng Hebrew.

Ví dụ:

```text
Đoạn A: ABC שלום XYZ    -> strong character đầu tiên là A (LTR)
Đoạn B: שלום Hello      -> strong character đầu tiên là ש (RTL)
Đoạn C: 123 - 45        -> không có chữ strong trong nội dung này
```

Với lựa chọn hướng mặc định dựa trên ký tự mạnh đầu tiên, A có base LTR, B có base RTL, còn C cần **fallback đã được chọn**.

### 2.3. Embedding level

Thuật toán hai chiều gán một **resolved embedding level** cho các vị trí văn bản. Nguyên tắc đọc đơn giản:

- Level **chẵn** biểu thị run theo chiều LTR.
- Level **lẻ** biểu thị run theo chiều RTL.
- Level cao hơn có thể đại diện một run nằm trong ngữ cảnh hướng ngược ở mức lồng sâu hơn.

Ví dụ level `2` vẫn là LTR, nhưng có thể là một đoạn LTR nằm bên trong ngữ cảnh RTL level `1`. Không nên đơn giản hóa thành “0 là Latin, 1 là Hebrew”; level là **kết quả thuật toán và ngữ cảnh**, không phải nhãn ngôn ngữ.

`Bidi` trình bày các run có cùng level qua `getRunCount()` và các phương thức truy vấn run. Các level là thông tin cần thiết cho khâu **visual reordering** khi layout.

## 3. Bốn hằng chọn hướng cơ sở của Bidi

Constructor đơn giản:

```java
import java.text.Bidi;

Bidi bidi = new Bidi(paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
```

Đây là đoạn minh họa bên trong phương thức, với biến `paragraph` kiểu `String`. Tham số thứ hai chọn chính sách hướng cơ sở.

| Hằng | Ý nghĩa |
| --- | --- |
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Ép base direction là LTR, base level `0` |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Ép base direction là RTL, base level `1` |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Tìm strong character đầu tiên; nếu không có thì fallback LTR |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Tìm strong character đầu tiên; nếu không có thì fallback RTL |

**Khác biệt quan trọng:** Hai hằng chứa chữ `DEFAULT` **không ép** mọi chuỗi sang LTR/RTL. Cả hai vẫn xét strong character đầu tiên; chúng chỉ khác hướng fallback khi **không tìm được strong character phù hợp**.

Ví dụ đoạn `"שלום Hello"` bắt đầu bằng Hebrew, vì vậy hướng cơ sở là RTL khi dùng cả `DIRECTION_DEFAULT_LEFT_TO_RIGHT` lẫn `DIRECTION_DEFAULT_RIGHT_TO_LEFT`.

Ngược lại, với `"123 - 45"` chỉ có chữ số/ký tự trung tính trong ví dụ, không có strong L/R/AL, nên hai default trả base level khác nhau.

### Bảng lựa chọn minh họa

| Văn bản logic | Cờ | Base level |
| --- | --- | --- |
| `ABC שלום XYZ` | `DEFAULT_LEFT_TO_RIGHT` | `0` |
| `שלום Hello` | `DEFAULT_LEFT_TO_RIGHT` | `1` |
| `שלום Hello` | `LEFT_TO_RIGHT` | `0` |
| `ABC שלום XYZ` | `RIGHT_TO_LEFT` | `1` |
| `123 - 45` | `DEFAULT_LEFT_TO_RIGHT` | `0` |
| `123 - 45` | `DEFAULT_RIGHT_TO_LEFT` | `1` |

Từ “ép” chỉ có nghĩa **chọn hướng nền của đoạn**, không có nghĩa biến chữ Hebrew thành thứ tự logic LTR hoặc biến mọi dấu trong chuỗi thành RTL.

### Khi nào nên chọn hướng tường minh?

Nếu một trường giao diện có **ngữ cảnh xác định** (ví dụ cả màn hình là Hebrew/Arabic, hoặc một ô nhập mã kỹ thuật luôn LTR), có thể chủ động truyền hướng cơ sở để punctuation/number và cách căn nội dung được xử lý nhất quán.

Nếu một trường nhận **văn bản đa ngôn ngữ tự do**, lựa chọn dựa trên strong character đầu tiên có thể phù hợp hơn, nhưng nên xác định một hướng fallback tương ứng với giao diện khi người dùng chỉ nhập số hoặc ký hiệu.

Không suy hướng văn bản chỉ từ `Locale`: locale của người dùng và nội dung đoạn không nhất thiết cùng ngôn ngữ. Người dùng giao diện tiếng Việt có thể nhập một câu Arabic; người dùng giao diện Arabic vẫn có thể nhập URL tiếng Anh.

## 4. Tạo Bidi và đọc base direction

Một ví dụ ngắn:

```java
String hebrew = "\u05E9\u05DC\u05D5\u05DD"; // שלום
Bidi left = new Bidi("ABC " + hebrew,
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

Bidi right = new Bidi(hebrew + " Hello",
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

System.out.println(left.getBaseLevel());
System.out.println(right.getBaseLevel());
```

Các lệnh nằm trong một phương thức với `import java.text.Bidi;`. Stdout:

```text
0
1
```

Ba phương thức cần hiểu:

- `getBaseLevel()` trả level nền: `0` cho LTR và `1` cho RTL.
- `baseIsLeftToRight()` trả `true` nếu hướng nền LTR.
- `isLeftToRight()` trả `true` khi **toàn bộ line** là LTR **và** hướng nền LTR.

Điểm thứ ba thường gây nhầm: `baseIsLeftToRight()` không đồng nghĩa `isLeftToRight()`. Một đoạn có base LTR nhưng có run Hebrew RTL sẽ thỏa:

```text
baseIsLeftToRight() = true
isLeftToRight()     = false
isMixed()           = true
```

Tương tự, `isRightToLeft()` chỉ trả true nếu line hoàn toàn RTL và base RTL. `isMixed()` trả true khi không thuần LTR và không thuần RTL; theo hợp đồng API, nó cũng có thể true nếu hướng nền khác với hướng của run duy nhất.

Vì vậy không dùng `isMixed()` để kết luận “chắc chắn có hai bảng chữ Latin và Arabic” hoặc “có ít nhất hai run”. Hãy đọc **base và các run thực tế**.

## 5. Đọc các run và embedding level

Một `Bidi` xử lý một paragraph/line cung cấp các phương thức:

| API | Ý nghĩa |
| --- | --- |
| `getLength()` | Độ dài text trong line theo chỉ số của `String` |
| `getBaseLevel()` | Level nền: 0 hay 1 |
| `getLevelAt(offset)` | Level được giải quyết tại vị trí offset |
| `getRunCount()` | Số run có cùng level |
| `getRunStart(run)` | Offset đầu của run |
| `getRunLimit(run)` | Offset **ngay sau** ký tự cuối run |
| `getRunLevel(run)` | Embedding level của run |
| `baseIsLeftToRight()` | Kiểm tra hướng nền |
| `isLeftToRight()` / `isRightToLeft()` | Kiểm tra line có thuần một hướng và base tương ứng không |
| `isMixed()` | Kiểm tra line không thuộc hai trường hợp thuần trên |

Offsets của run dùng khoảng **nửa mở** `[start, limit)`. Có thể dùng trực tiếp `substring(start, limit)` để xem văn bản ở thứ tự logic của từng run.

Ví dụ với:

```text
ABC שלום XYZ
```

Trên JDK được dùng để kiểm tra, Bidi trả ba run:

| Run index | Start | Limit | Level | Phần văn bản logic |
| --- | --- | --- | --- | --- |
| 0 | 0 | 4 | 0 | `ABC ` |
| 1 | 4 | 8 | 1 | `שלום` |
| 2 | 8 | 12 | 0 | ` XYZ` |

Run `1` có level lẻ, nên thuộc RTL. Hai run `0` và `2` có level chẵn, nên thuộc LTR.

**Đừng đọc thứ tự danh sách run như một chuỗi “đã hiển thị hoàn chỉnh”.** `getRunStart/getRunLimit` cho biết phần logic của run, còn việc xếp các run theo visual order và vẽ glyph là các bước tiếp theo của bộ máy trình bày.

### Offset là chỉ số Java UTF-16

`String.length()` và `substring(...)` sử dụng offset UTF-16, không phải số grapheme người dùng nhìn thấy. `getRunStart` và `getRunLimit` cũng dùng offset của đoạn văn mà `Bidi` phân tích.

Ví dụ Hebrew `שלום` trong bài có bốn ký tự BMP, nên mỗi chữ tương ứng một code unit. Với emoji hoặc code point bổ sung nằm trong chuỗi, không được giả định mỗi ký tự người dùng thấy chiếm một offset. Tránh dùng offset của `Bidi` như chỉ số code point khi thao tác với `String.codePoints()` mà chưa chuyển đổi.

## 6. Ví dụ Java 17+ chạy độc lập

Tạo tệp `BidiBaseDirectionDemo.java`. Các ký tự Hebrew dùng Unicode escape trong source để dễ biên dịch mà không phụ thuộc terminal hiển thị chúng thế nào. Chương trình in **chỉ số run** thay vì cố in “chuỗi hình ảnh RTL”, vì cách hiển thị ở terminal còn phụ thuộc console.

```java
import java.text.Bidi;
import java.util.Arrays;

public class BidiBaseDirectionDemo {
    public static void main(String[] args) {
        String hebrew = "\u05E9\u05DC\u05D5\u05DD";
        String text = "ABC " + hebrew + " XYZ";

        Bidi bidi = new Bidi(
                text, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("base=" + bidi.getBaseLevel());
        System.out.println("mixed=" + bidi.isMixed());

        for (int run = 0; run < bidi.getRunCount(); run++) {
            System.out.println("run " + run
                    + "=[" + bidi.getRunStart(run)
                    + "," + bidi.getRunLimit(run) + ")"
                    + " level=" + bidi.getRunLevel(run));
        }

        Bidi rtlFirst = new Bidi(
                hebrew + " Hello",
                Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println(
                "first RTL base=" + rtlFirst.getBaseLevel());

        String neutral = "123 - 45";

        System.out.println("neutral default LTR="
                + new Bidi(neutral,
                    Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT)
                  .getBaseLevel());

        System.out.println("neutral default RTL="
                + new Bidi(neutral,
                    Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT)
                  .getBaseLevel());

        Bidi forced = new Bidi(
                text, Bidi.DIRECTION_RIGHT_TO_LEFT);

        System.out.println("forced base="
                + forced.getBaseLevel());

        Object[] pieces = {"A", "B", "C", "D"};
        byte[] levels = {0, 1, 1, 0};
        Bidi.reorderVisually(
                levels, 0, pieces, 0, pieces.length);

        System.out.println("visual runs="
                + Arrays.toString(pieces));

        System.out.println("requires Hebrew="
                + Bidi.requiresBidi(
                    hebrew.toCharArray(), 0, hebrew.length()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BidiBaseDirectionDemo.java
java BidiBaseDirectionDemo
```

Stdout đã kiểm tra:

```text
base=0
mixed=true
run 0=[0,4) level=0
run 1=[4,8) level=1
run 2=[8,12) level=0
first RTL base=1
neutral default LTR=0
neutral default RTL=1
forced base=1
visual runs=[A, C, B, D]
requires Hebrew=true
```

### Diễn giải từng nhóm

- `base=0`: ký tự strong đầu tiên của `ABC שלום XYZ` là `A`, nên hướng nền LTR.
- `mixed=true`: text gồm một run Hebrew RTL giữa các run Latin LTR.
- Các dòng `run` cho biết offsets và level trong thứ tự logic: run 0 `[0,4)`, run 1 `[4,8)`, run 2 `[8,12)`.
- `first RTL base=1`: khi strong character đầu là Hebrew, default hướng cơ sở là RTL.
- Hai dòng `neutral` cho thấy khác nhau giữa fallback LTR và RTL khi đầu vào `123 - 45` không có strong L/R/AL.
- `forced base=1`: lựa chọn `DIRECTION_RIGHT_TO_LEFT` ấn định hướng nền RTL ngay cả khi chuỗi bắt đầu bằng Latin.
- `visual runs=[A, C, B, D]` minh họa cách `reorderVisually` đổi thứ tự **bốn object/run giả lập** với levels `{0,1,1,0}`: hai object ở level 1 được đổi thứ tự ở khâu visual reordering.
- `requires Hebrew=true` chứng minh đoạn Hebrew cần xử lý bidi; không phải chứng minh nó đã được vẽ đúng glyph.

Chương trình minh họa kết quả API chứ không thực hiện renderer hoàn chỉnh. Không suy từ chuỗi `[A, C, B, D]` rằng nên đảo từng ký tự của văn bản nguồn.

## 7. requiresBidi là bước kiểm tra nhanh, không phải hiển thị

`Bidi.requiresBidi(char[] text, int start, int limit)` kiểm tra vùng ký tự có cần phân tích bidi hay không. Nó có thể giúp bỏ qua việc tạo đối tượng `Bidi` trong một pipeline layout chỉ có dữ liệu LTR đơn giản.

Ví dụ:

```java
char[] latin = "Hello".toCharArray();
char[] hebrew = "\u05E9\u05DC\u05D5\u05DD".toCharArray();

System.out.println(Bidi.requiresBidi(
        latin, 0, latin.length));
System.out.println(Bidi.requiresBidi(
        hebrew, 0, hebrew.length));
```

Trong phương thức có import `java.text.Bidi`, kết quả:

```text
false
true
```

**Nhưng `requiresBidi` không phải parser ngôn ngữ, không xác nhận Unicode hợp lệ, không kiểm tra ký tự nguy hiểm và không quyết định rằng UI phải căn trái/phải.** Nó là một phép kiểm tra phục vụ layout. `false` không có nghĩa chuỗi chỉ chứa ASCII hoặc không có dấu tiếng Việt; nhiều văn bản Unicode vẫn có thể hoàn toàn LTR.

Không gọi `requiresBidi` rồi đổi byte hoặc đảo `String` nếu trả `true`. Nó không làm bước render thay bạn.

## 8. reorderVisually: sắp thứ tự run, không đảo code point

Phương thức static:

```java
Bidi.reorderVisually(
        byte[] levels,
        int levelStart,
        Object[] objects,
        int objectStart,
        int count);
```

nêu trên có chức năng sắp **đối tượng đại diện run** theo visual order dựa trên level tương ứng. Nó không tự biết nội dung Unicode bên trong một object và không tự tạo glyph, không gắn dấu kết hợp hay thực hiện Arabic shaping.

Ví dụ dễ quan sát:

```java
Object[] pieces = {"A", "B", "C", "D"};
byte[] levels = {0, 1, 1, 0};

Bidi.reorderVisually(levels, 0, pieces, 0, pieces.length);
System.out.println(Arrays.toString(pieces));
```

Trong phương thức có import `Bidi` và `Arrays`, kết quả là:

```text
[A, C, B, D]
```

Việc hai object `B` và `C` đổi vị trí xuất phát từ level lẻ ở dải liên tiếp; không phải phép đảo chuỗi tùy ý.

Cần phân biệt:

- **Logical order:** vị trí gốc của ký tự trong `String`.
- **Resolved levels:** hướng và mức lồng sau khi áp dụng thuật toán.
- **Visual order của các run:** thứ tự bố trí các run sau phân tích.
- **Visual order/glyph trong từng run:** phần việc của bộ máy text layout, kết hợp shaping, font, script và rendering.

`reorderVisually` chỉ hỗ trợ một phần pipeline. Không thay thế thuật toán hai chiều bằng `Collections.reverse` hoặc dùng `StringBuilder.reverse()` với đoạn Arabic/Hebrew: các thao tác đó phá thứ tự logic và có thể làm hỏng dấu kết hợp hoặc surrogate pair.

## 9. createLineBidi: hướng đoạn và xuống dòng

Thuật toán Unicode bidi có quan hệ với **đoạn văn (paragraph)** và **dòng hiển thị (line)**. Khi layout text dài, ứng dụng có thể:

1. Phân tích đoạn theo hướng cơ sở phù hợp.
2. Chọn điểm ngắt dòng dựa trên chiều rộng, font và quy tắc line breaking.
3. Tạo thông tin bidi cho từng dòng cần vẽ.
4. Sắp xếp và vẽ các run trên từng dòng.

`Bidi.createLineBidi(lineStart, lineLimit)` tạo một đối tượng Bidi đại diện một **dòng con** trong paragraph đã được phân tích:

```java
Bidi paragraphBidi = new Bidi(
        paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

Bidi lineBidi = paragraphBidi.createLineBidi(
        lineStart, lineLimit);
```

Đây là đoạn minh họa trong một phương thức có `paragraph`, `lineStart` và `lineLimit` đã được xác định bởi bộ layout. Hai offset chỉ giới hạn phần text của dòng trong paragraph; không phải tọa độ pixel trên màn hình.

Nếu toàn paragraph nằm trên một dòng, bạn không bắt buộc phải tạo `createLineBidi`. Nhưng khi text wrap thành nhiều dòng, quá trình xử lý bidi cho từng dòng có thể có quy tắc điều chỉnh các ký tự ở cuối dòng (như whitespace) và khác với việc dùng một danh sách run của toàn paragraph như thể đó là một dòng duy nhất.

**Không tự chia paragraph bằng số `char` cố định rồi cho rằng đã layout đúng.** Ngắt dòng còn liên quan độ rộng glyph, font, chữ ghép, grapheme cluster, hyphenation, dấu câu và quy tắc xuống dòng. `Bidi` không cung cấp trình bày văn bản đa dòng đầy đủ.

## 10. Các constructor khác và thuộc tính văn bản

Ngoài `Bidi(String, flags)`, Java còn có những constructor phục vụ pipeline text phức tạp:

```java
new Bidi(
        char[] text,
        int textStart,
        byte[] embeddings,
        int embStart,
        int paragraphLength,
        int flags);
```

và:

```java
new Bidi(AttributedCharacterIterator paragraph);
```

Đây là chữ ký constructor minh họa, không phải lời gọi độc lập với các biến chưa khai báo.

Constructor nhận mảng cho phép cung cấp thông tin embedding; constructor nhận `AttributedCharacterIterator` có thể đọc các thuộc tính văn bản. Những thuộc tính liên quan từ `java.awt.font.TextAttribute` bao gồm:

- `TextAttribute.RUN_DIRECTION`: hướng cơ sở được chỉ định.
- `TextAttribute.BIDI_EMBEDDING`: thông tin embedding hoặc override khi cần.
- `TextAttribute.NUMERIC_SHAPING`: yêu cầu xử lý hình dạng chữ số trong pipeline liên quan.

Các tính năng này dành cho hệ thống layout có yêu cầu thực sự và cần kiểm tra khả năng tương thích. Với việc đơn thuần phân tích một chuỗi văn bản và hướng cơ sở, constructor `Bidi(String, flags)` thường đủ rõ.

### Embedding không giống thay đổi chuỗi gốc

Embedding level bổ sung cách hiểu/bố trí văn bản, không làm code point của chuỗi Hebrew trở thành ký tự Latin. Đừng sửa dãy ký tự trong `String` chỉ để “áp” một level. Khi xuất data sang API hoặc database, lưu chuỗi theo **thứ tự logic**, và lưu metadata hướng riêng nếu cần để tái tạo cách hiển thị.

## 11. Số, dấu câu và đoạn RTL

Các dấu như `:`, `(`, `)`, `-`, khoảng trắng và dấu ngoặc kép thường không có hướng mạnh. Cùng một chuỗi chứa số có thể hiển thị các dấu đó khác nhau khi base RTL hoặc LTR.

Một vài tình huống thường gặp:

### 11.1. Nhãn tiếng Hebrew/Arabic kèm số

Ví dụ một câu RTL có mã đơn hàng `AB-123`. Mã kỹ thuật là một chuỗi LTR có dấu gạch nối, còn câu xung quanh là RTL. Nếu chỉ nối chuỗi:

```java
String message = rtlText + ": " + orderId;
```

đây là đoạn minh họa trong một phương thức với các biến đã có. Kết quả hiển thị dấu hai chấm, dấu gạch nối và mã có thể phụ thuộc base direction và bidi context của UI. Trong giao diện thật, nên đặt mã trong thành phần có **direction/isolation rõ ràng** thay vì dựa vào việc đổi dấu cách để sửa hình ảnh.

### 11.2. URL, email và tên file

URL `https://example.com/a?x=1`, địa chỉ email, đường dẫn file và mã sản phẩm thường là dữ liệu có cú pháp LTR. Khi xuất hiện trong câu RTL, cách **cô lập** phần dữ liệu đó có thể cần được định nghĩa ở tầng render.

Không nên đảo URL ở tầng dữ liệu hoặc tự đảo từng đoạn của nó. Thứ tự logic của URL phải giữ nguyên để hoạt động của link, copy/paste và parser không bị phá.

### 11.3. Một đoạn chỉ có số hoặc dấu trung tính

Với `"123 - 45"`, `DIRECTION_DEFAULT_LEFT_TO_RIGHT` và `DIRECTION_DEFAULT_RIGHT_TO_LEFT` có thể tạo hai base level khác nhau do không có strong letter quyết định hướng.

Nếu trường input chỉ nhận số nhưng được hiển thị bên trong trang RTL, có thể cần chọn chính sách direction riêng (đặc biệt với dấu âm, dấu phần trăm, đơn vị). **Không lấy dấu của số làm căn cứ tự động suy hướng của toàn đoạn.**

### 11.4. Dấu ngoặc

Các dấu ngoặc có thể được xử lý theo quy tắc cặp ngoặc của thuật toán Unicode. Số và chữ Latin xen trong câu RTL có thể khiến dấu ngoặc trông di chuyển hoặc được mirror trong quá trình vẽ.

`Bidi` cung cấp level/run, còn việc hiển thị đúng glyph phản chiếu và các chi tiết font/render vẫn thuộc bộ máy text layout. Không giả định `Bidi` có phương thức tự “sửa dấu ngoặc” trong `String`.

## 12. Bidi analysis không phải text rendering

Đây là ranh giới kỹ thuật quan trọng:

| Việc cần làm | `java.text.Bidi` có giải quyết trực tiếp? |
| --- | --- |
| Xác định hướng nền của paragraph | Có |
| Xác định level và ranh giới directional run | Có |
| Hỗ trợ đổi thứ tự object/run theo level | Có, qua `reorderVisually` |
| Chọn font có glyph Hebrew/Arabic | Không |
| Ghép dạng chữ Arabic theo ngữ cảnh (*shaping*) | Không phải renderer |
| Tính bề rộng glyph để xuống dòng | Không |
| Vẽ ký tự trên màn hình | Không |
| Quyết định căn trái/phải của widget | Không |
| Chọn `Locale` hiển thị cho người dùng | Không |
| Bảo vệ khỏi mọi hình thức Unicode spoofing | Không |

Trong ứng dụng GUI, hệ thống rendering như Java2D text layout, Swing hoặc framework UI thường cung cấp những tầng xử lý riêng. Tùy thành phần, có thể cần thuộc tính hướng và component orientation của giao diện, text layout, font shaping và caret behavior.

Nếu app viết HTML, cơ chế tương ứng ở tầng trình duyệt gồm `dir`, cách cô lập nội dung trộn chiều và những thuộc tính layout liên quan. `Bidi` của Java không tự đặt `dir` trên DOM; đó là trách nhiệm của tầng xuất HTML.

**Không dùng kết quả `getBaseLevel()` thay thế toàn bộ logic layout của UI.** Một paragraph base RTL không nhất thiết có mọi widget căn phải, mọi cột đảo vị trí hoặc mọi icon được mirror. Thiết kế RTL đầy đủ còn bao gồm flow layout, vị trí điều khiển, tab order, biểu tượng điều hướng và khả năng tiếp cận.

## 13. Hướng tự động và hướng UI: hai quyết định khác nhau

Giả sử ứng dụng có giao diện tiếng Việt nhưng một người dùng nhập tiêu đề tiếng Arabic. Nếu trường nội dung dùng chính sách `DIRECTION_DEFAULT_LEFT_TO_RIGHT`, ký tự strong đầu tiên của tiêu đề có thể khiến paragraph chọn base RTL. Điều này có thể hữu ích để vẽ câu.

Nhưng:

- **Ngôn ngữ giao diện** vẫn có thể là tiếng Việt.
- **Hướng nội dung nhập** có thể là RTL.
- **Hướng layout của biểu mẫu** vẫn có thể LTR.
- **Hướng của một mã kỹ thuật bên trong câu** có thể cần LTR isolation.

Không nên gọi `Locale.setDefault` để “đổi hướng cả ứng dụng” theo người dùng. Locale chứa thông tin ngôn ngữ/vùng, không phải một công tắc thay thế điều khiển bidi của tất cả thành phần.

Một ứng dụng cần chính sách rõ cho từng loại trường:

| Loại dữ liệu | Chính sách gợi ý |
| --- | --- |
| Đoạn văn tự do | Hướng tự động theo strong character đầu tiên, fallback theo ngữ cảnh UI |
| Địa chỉ email, URL, ID có grammar LTR | Render trong vùng LTR được cô lập |
| Nhãn ứng dụng đã dịch | Hướng theo ngôn ngữ của nhãn/thiết kế màn hình |
| Ô số có dấu âm, đơn vị | Kiểm tra thực tế với direction của biểu mẫu |
| Văn bản thuần chỉ có ký hiệu | Hướng cơ sở fallback nên xác định thay vì đoán |

Các ví dụ là **định hướng thiết kế**, không phải luật bắt buộc cho tất cả ứng dụng. Cần thử trên framework cụ thể vì hành vi layout của widget có thể khác nhau.

## 14. Unicode bidi controls và an toàn hiển thị

Unicode có các ký tự điều khiển hướng ảnh hưởng đến cách văn bản được hiển thị, trong đó có:

| Nhóm | Một số code point | Vai trò khái quát |
| --- | --- | --- |
| Mark | `LRM U+200E`, `RLM U+200F`, `ALM U+061C` | Đánh dấu hướng trong ngữ cảnh |
| Embedding/override | `LRE U+202A`, `RLE U+202B`, `LRO U+202D`, `RLO U+202E`, `PDF U+202C` | Điều khiển embedding/override kiểu cũ |
| Isolate | `LRI U+2066`, `RLI U+2067`, `FSI U+2068`, `PDI U+2069` | Cô lập đoạn có hướng trong thuật toán Unicode |

Những ký tự này có thể **không hiện thành hình glyph bình thường**, nhưng vẫn ảnh hưởng đến thứ tự nhìn thấy. Đặc biệt các kiểu override có thể khiến văn bản hiển thị theo thứ tự khác điều người đọc suy từ ký tự logic.

### Rủi ro giả mạo cách nhìn

Trong tên file, thông báo log, đoạn code hay nội dung người dùng cung cấp, một chuỗi điều khiển bidi có thể khiến phần mở rộng file, dấu câu hoặc một phần câu được nhìn ở vị trí bất ngờ. Đây là một trong những nguy cơ **visual spoofing** khi nội dung được nhìn khác thứ tự lưu trữ.

Vì vậy:

1. **Giữ thứ tự logic của dữ liệu** khi lưu và truyền.
2. Không tự thêm các ký tự override để “sửa hiển thị” một cách tùy tiện.
3. Khi hiển thị nội dung không tin cậy, dùng **text isolation hoặc container direction** phù hợp ở tầng renderer.
4. Trong công cụ dành cho developer/kiểm toán, có thể cần hiển thị hoặc escape các ký tự điều khiển khi debug, ví dụ dạng `U+202E`.
5. Với những định danh có yêu cầu an toàn, quy định rõ ký tự điều khiển nào được phép và xử lý theo schema; không nên lặng lẽ cho phép mọi invisible control.
6. Khi làm sạch đầu vào, không “xóa mọi ký tự điều khiển bidi” một cách mù quáng nếu chúng có ý nghĩa trong văn bản đa ngôn ngữ hợp lệ; hãy áp dụng chính sách theo miền dữ liệu.

**`Bidi` không phải API chống spoofing**. Phân tích đúng các run không chứng minh thông điệp hiển thị an toàn cho mọi trường hợp. Hệ thống cần phối hợp kiểm tra input, isolation, escaping, font/render và cách hiển thị ký tự không in được khi phù hợp.

### Isolation khác override

*Isolate* giúp một đoạn được xử lý như một vùng định hướng riêng, hạn chế việc nội dung bên trong tác động không mong muốn đến ngữ cảnh xung quanh. *Override* ép loại hướng của ký tự trong phạm vi tác động. Chúng có ý nghĩa khác nhau và không thể thay thế tùy tiện.

Trong các UI hiện đại, các cơ chế isolation ở tầng presentation thường phù hợp hơn việc nhét nhiều ký tự override vào text gốc. Mặt khác, `Bidi` của Java 17 và renderer đang dùng cần được kiểm thử với những control hiện đại cụ thể; không suy rằng mọi engine cũ đều triển khai giống nhau mọi phiên bản UAX #9.

## 15. Kiểm thử bidi đúng cách

Test bidi không nên chỉ nhìn stdout text của console: terminal có thể tự áp dụng thuật toán, font và ngữ cảnh hướng, khiến thứ tự quan sát khác nhau giữa Windows Terminal, IDE và CI.

Có thể tách ba lớp kiểm thử:

### 15.1. Unit test thuật toán/metadata

Kiểm tra giá trị xác định của `Bidi`:

- `getBaseLevel()` với đoạn bắt đầu Latin, Hebrew/Arabic và đoạn toàn ký tự trung tính.
- `getRunCount()`, `getRunStart()`, `getRunLimit()` và `getRunLevel()` ở ví dụ được kiểm soát.
- `baseIsLeftToRight()` so với `isLeftToRight()`/`isMixed()`.
- `requiresBidi(...)` cho text LTR và text RTL.
- `reorderVisually(...)` với tập level giả lập.
- `createLineBidi(...)` khi một paragraph được wrap thành nhiều dòng.

Không hard-code kết quả level chi tiết cho mọi chuỗi Unicode thực tế xuyên mọi phiên bản JDK nếu chương trình không khóa bộ quy tắc/dữ liệu Unicode tương ứng. Các ca minh họa đơn giản là mốc kiểm tra hữu ích, nhưng hệ thống sản phẩm còn cần QA trực quan.

### 15.2. Integration test renderer

Kiểm tra đầu ra của framework đang dùng với:

- Câu Hebrew/Arabic chứa số Latin.
- URL hoặc email trong câu RTL.
- Dấu ngoặc quanh từ LTR nằm trong câu RTL.
- Văn bản có nhiều khoảng trắng và dấu câu trung tính ở hai đầu.
- Đoạn văn bị wrap thành hai hoặc nhiều dòng.
- Cursor/caret, chọn đoạn, copy/paste và đọc bằng screen reader.
- Font fallback và glyph shaping cho Arabic/Hebrew.
- Nội dung có bidi controls, bao gồm dữ liệu không tin cậy.

### 15.3. Test dữ liệu và bảo mật

Kiểm tra:

- Chuỗi sau khi format vẫn giữ **logical order** khi lưu/trao đổi.
- Phần text người dùng nhập được cô lập khỏi văn bản định dạng xung quanh.
- Tên file, domain, ID và thông báo log không gây nhầm lẫn khi chứa control vô hình.
- Chính sách cho ký tự bidi đặc biệt không vô tình phá khả năng nhập ngôn ngữ RTL hợp lệ.
- Mô tả accessibility/copy/paste không bị đảo logic so với dữ liệu gốc.

Screenshot có thể có ích trong UI test, nhưng **không thay** việc in code point hoặc kiểm tra raw string khi điều tra lỗi dữ liệu.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách phù hợp |
| --- | --- | --- |
| Đảo `String` để hiển thị Hebrew/Arabic | Phá logical order và nội dung lồng chiều | Dùng text layout hỗ trợ bidi |
| Tưởng `Bidi` vẽ được chữ | Lớp chỉ cung cấp thông tin phân tích/reordering | Dùng renderer có shaping/font/layout |
| Đồng nhất base RTL với mọi run RTL | Có thể có LTR run ở level chẵn bên trong | Đọc run và level |
| Nghĩ `DIRECTION_DEFAULT_LEFT_TO_RIGHT` luôn LTR | Vẫn xét strong character đầu tiên | Hiểu fallback chỉ dùng khi không có strong |
| Nghĩ ký tự đầu chuỗi luôn quyết định hướng | Đầu chuỗi có thể là số/dấu trung tính | Xét ký tự strong và ngữ cảnh |
| Nghĩ `isMixed()` nghĩa “ít nhất hai ngôn ngữ” | Có thể mixed do hướng base khác run duy nhất | Dùng định nghĩa API và run |
| Coi run index là visual-order string | Run offsets tham chiếu logical-order text | Kết hợp level và renderer |
| Dùng `getRunLimit` như offset cuối inclusive | Limit là exclusive | Dùng `substring(start, limit)` |
| Nhầm UTF-16 offset với số grapheme | Code point bổ sung/combining mark có độ dài khác | Chuyển đổi chỉ số đúng cách |
| Dùng `Locale` để suy toàn bộ hướng UI | Nội dung và ngôn ngữ giao diện có thể khác | Có policy direction riêng |
| Đảo URL hoặc số trong câu RTL bằng tay | Phá grammar và copy/paste | Cô lập run LTR ở tầng render |
| Tự đổi dấu ngoặc trong dữ liệu để “sửa” bidi | Có thể làm sai logical order | Để bộ máy layout xử lý mirroring |
| Xem `requiresBidi` là công cụ kiểm tra an toàn | Chỉ báo nhu cầu phân tích bidi | Tách validation/security |
| Tự thêm RLO/LRO để định dạng mọi dòng | Tăng rủi ro spoofing và layout khó đoán | Ưu tiên isolation/container direction |
| Chỉ kiểm tra stdout ở console | Console có thể render khác UI | Kết hợp metadata test và visual QA |
| Dùng `reorderVisually` để đảo ký tự | Phương thức sắp object/run theo level | Không thay bộ máy shaping/rendering |

## 17. Bài tập thực hành

**Bài 1 — hướng mặc định.** Tạo ba `Bidi` từ `"ABC שלום"`, `"שלום ABC"` và `"123 - 45"` với `DIRECTION_DEFAULT_LEFT_TO_RIGHT`. Dự đoán base level; sau đó đổi chuỗi trung tính sang `DIRECTION_DEFAULT_RIGHT_TO_LEFT` và giải thích kết quả.

**Bài 2 — ép hướng.** Dùng cùng `"ABC שלום XYZ"`, tạo một đối tượng với `DIRECTION_LEFT_TO_RIGHT` và một với `DIRECTION_RIGHT_TO_LEFT`. So sánh `getBaseLevel()`, `getRunCount()` và những level có thể thay đổi. Vì sao không nên sửa `String` gốc?

**Bài 3 — phân tích run.** Dùng ví dụ Java ở trên, ghi lại ba khoảng `[start, limit)`. Lấy phần văn bản của từng run bằng `substring` và giải thích parity của level. Vì sao `getRunLimit` không phải index inclusive?

**Bài 4 — pure direction và mixed.** Tạo chuỗi toàn Latin, toàn Hebrew và hỗn hợp. Kiểm tra `isLeftToRight()`, `isRightToLeft()`, `isMixed()` và `baseIsLeftToRight()`. Hãy giải thích trường hợp một đoạn có base LTR mà không thuần LTR.

**Bài 5 — reorderVisually.** Cho objects `{"A","B","C","D"}` và levels `{0,1,1,0}`. Dự đoán thứ tự sau `reorderVisually`. Vì sao đó là phép sắp object theo level chứ không phải đảo từng code point?

**Bài 6 — số và URL.** Thiết kế một nhãn tiếng Arabic có số tiền và một URL tiếng Anh. Những phần nào cần hướng nền RTL, phần nào cần isolation LTR? Vì sao không nên đơn giản nối chuỗi rồi thêm khoảng trắng nếu dấu câu bị đặt sai?

**Bài 7 — multi-line.** Giả sử paragraph có text hỗn hợp và được wrap thành nhiều dòng. `createLineBidi` cung cấp thông tin gì cho từng dòng? Các thông tin nào còn cần từ hệ thống đo glyph và line breaking?

**Bài 8 — kiểm tra an toàn.** Một tên file chứa `U+202E` hoặc một control bidi khác. Đề xuất cách hiển thị cho người dùng và log cho developer để tránh nhầm phần mở rộng, nhưng vẫn xử lý đúng văn bản RTL hợp lệ.

## 18. Kết luận

`java.text.Bidi` thực hiện **phân tích hai chiều Unicode** đối với một đoạn văn bản, xác định hướng cơ sở, embedding level và các run dùng trong việc bố trí văn bản hỗn hợp LTR/RTL. Hướng cơ sở có thể được chỉ định tường minh hoặc suy từ strong character đầu tiên với fallback phù hợp.

**Hướng cơ sở không phải hướng của mọi ký tự.** Ngay trong câu RTL vẫn có thể có số và run Latin LTR. `getBaseLevel()`, `getRunLevel()` và các offset run mô tả **cách tổ chức để hiển thị**, không sửa thứ tự logic của `String`.

Với ứng dụng thực tế, hãy giữ văn bản theo logical order, sử dụng renderer hỗ trợ bidi và shaping, cô lập nội dung nhúng khác hướng, xác định chính sách UI direction riêng với locale, và kiểm thử cả metadata lẫn giao diện. Không dùng đảo chuỗi hoặc bidi override tùy tiện để bù cho lỗi layout.

**Nguyên tắc ghi nhớ:** *Bidi phân tích hướng để hiển thị; dữ liệu vẫn giữ thứ tự logic; base direction là nền, không phải mệnh lệnh đảo toàn bộ chuỗi.*

### Tài liệu tham khảo

- [`java.text.Bidi` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html)
- [Unicode Bidirectional Algorithm – UAX #9](https://www.unicode.org/reports/tr9/)
- [Unicode FAQ: Writing Direction and Bidirectional Text](https://www.unicode.org/faq/bidi.html)
