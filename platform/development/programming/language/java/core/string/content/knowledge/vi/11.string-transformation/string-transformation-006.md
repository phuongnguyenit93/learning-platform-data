# Thay đổi độ dài sau biến đổi `String` và tác động đến chỉ số cũ

## 1. Mục tiêu

Trong Java, `String` là **bất biến**: các thao tác như `replace()`, `toUpperCase()`, `strip()` hoặc Unicode normalization trả về giá trị chuỗi kết quả, thay vì chỉnh sửa trực tiếp nội dung đối tượng chuỗi cũ. **Chuỗi kết quả có thể dài hơn hoặc ngắn hơn chuỗi ban đầu**.

Nếu bạn ghi nhớ chỉ số của một ký tự, token hoặc vùng chọn từ chuỗi ban đầu rồi tiếp tục sử dụng nó trên chuỗi sau biến đổi, chỉ số đó có thể **trỏ sai ký tự, cắt sai vùng hoặc vượt giới hạn**.

Ví dụ ngắn:

```java
import java.util.Locale;

String original = "Stra\u00DFe|END";          // Straße|END
int oldSeparator = original.indexOf('|'); // 6

String changed = original.toUpperCase(Locale.ROOT);
// "STRASSE|END": ß biến thành SS; có thêm 1 char.

System.out.println(oldSeparator);              // 6
System.out.println(changed.indexOf('|'));       // 7
System.out.println(changed.charAt(oldSeparator)); // E
```

Chỉ số `6` vẫn hợp lệ về mặt giới hạn nhưng **không còn trỏ đến dấu `|`**. Đây là lỗi nguy hiểm hơn chỉ số vượt mảng, bởi chương trình có thể chạy bình thường nhưng trả kết quả sai.

Sau bài học, bạn có thể:
- Phân biệt độ dài `String.length()`, số Unicode code point và số ký tự hiển thị.
- Nhận biết các phép biến đổi có thể thay đổi số UTF-16 code unit.
- Hiểu sự lệch chỉ số khi ký tự **trước** vị trí đã lưu được thêm, xóa hoặc mở rộng.
- Viết code tìm lại ranh giới trên chuỗi đã biến đổi và biết khi nào cần mô hình ánh xạ vị trí có chủ đích.
- Tránh nhầm việc chuyển đổi chỉ số theo code point với việc ánh xạ vị trí **qua hai phiên bản chuỗi khác nhau**.

## 2. Chỉ số trong `String` là chỉ số UTF-16

`String.length()` trả về số **UTF-16 code unit** (đơn vị `char` 16 bit). Các API như `charAt(index)`, `substring(begin, end)`, `indexOf(...)` và vị trí trả về từ `Matcher.start()/end()` cũng sử dụng chỉ số UTF-16.

Một Unicode code point có thể chiếm **một hoặc hai `char`**; một ký tự người dùng nhìn thấy (*grapheme cluster*) có thể gồm nhiều code point.

| Chuỗi | `length()` (UTF-16 units) | Số code point | Vì sao? |
| --- | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | Mỗi chữ ASCII cần một `char`. |
| `"A🚀B"` | 4 | 3 | `🚀` là code point ngoài BMP, cần hai `char`. |
| `"\u00E9"` (é) | 1 | 1 | Dạng dựng sẵn U+00E9. |
| `"e\u0301"` (e + dấu sắc) | 2 | 2 | Một chữ nhìn thấy được có thể dùng hai code point. |

Vì vậy, **“độ dài thay đổi” phải được hiểu theo đơn vị đo**. Nếu một phép biến đổi đổi một code point thành hai code point (`ß` → `SS`), `length()` tăng một. Nếu một chuỗi ghép dấu được chuẩn hóa thành ký tự dựng sẵn (`e` + dấu sắc → `é`), `length()` giảm một. Nếu thay `"A"` bằng `"🚀"`, số code point vẫn là một nhưng `length()` tăng từ `1` lên `2`.

## 3. Những phép biến đổi có thể làm thay đổi độ dài

| Phép biến đổi | Ví dụ | Tác động có thể xảy ra |
| --- | --- | --- |
| `replace(CharSequence, CharSequence)` | `"abc".replace("b", "XYZ")` → `"aXYZc"` | Một đoạn nguồn có thể thành đoạn dài/ngắn hơn. |
| `replaceAll(regex, replacement)` | `"a  b".replaceAll(" +", " ")` → `"a b"` | Các lần khớp regex có thể làm độ dài thay đổi; cần chú ý cú pháp regex và replacement. |
| `toUpperCase(Locale)` | `"Straße"` → `"STRASSE"` với `Locale.ROOT` | Một ký tự có thể ánh xạ thành nhiều ký tự. |
| `toLowerCase(Locale)` | Một số biến thể Unicode hoặc quy tắc locale | Biến đổi toàn chuỗi có thể tạo số code point khác trước. |
| `strip()`, `stripLeading()`, `stripTrailing()` | `"  Java  ".strip()` → `"Java"` | Xóa các code point phù hợp ở biên. |
| `trim()` | `"  Java  ".trim()` → `"Java"` | Xóa các code unit có giá trị `<= U+0020` ở biên. |
| `Normalizer.normalize(..., NFC)` | `"e\u0301"` → `"\u00E9"` | Ghép các biểu diễn tương đương, có thể rút ngắn. |
| `Normalizer.normalize(..., NFD)` | `"\u00E9"` → `"e\u0301"` | Tách ký tự, có thể kéo dài. |
| `substring(begin, end)` | `"ABCDE".substring(1, 3)` → `"BC"` | Tạo chuỗi của một vùng được chọn; chỉ số mới được tính từ `0`. |
| `repeat(int)` | `"AB".repeat(3)` → `"ABABAB"` | Độ dài có thể tăng theo số lần lặp. |

**Chú ý:** `String` nguồn vẫn giữ nguyên nội dung, do đó chỉ số cũ vẫn có cùng ý nghĩa **trên chính nguồn cũ**. Nó trở thành vấn đề khi áp dụng cho **chuỗi kết quả mới**.

Một phép biến đổi cụ thể đôi khi không làm đổi độ dài. Ví dụ `"java".toUpperCase(Locale.ROOT)` vẫn dài 4. Không được vì một vài ví dụ đơn giản mà suy ra mọi phép chuyển hoa/thường đều bảo toàn độ dài.

## 4. Cơ chế lệch vị trí: thêm, xóa hoặc thay trước chỉ số

Giả sử trong chuỗi gốc, bạn lưu một vị trí `p`. Một phép biến đổi chỉ xảy ra **trước** vị trí đó, thay đoạn nguồn dài `oldSize` UTF-16 code unit bằng đoạn mới dài `newSize`. Nếu phép biến đổi là một lần thay thế đơn giản và không đụng đến chính ký tự mục tiêu, vị trí mới là:

```text
newIndex = oldIndex + (newSize - oldSize)
```

Ví dụ nguồn `"ABC|END"`, chỉ số của `|` là `3`:
- Thay `"ABC"` bằng `"ABCDE"`: chèn thêm hai code unit trước dấu `|`, vị trí mới là `5`.
- Thay `"ABC"` bằng `"X"`: giảm hai code unit, vị trí mới là `1`.
- Sửa một vùng **nằm hoàn toàn sau** dấu `|`: vị trí của dấu `|` không đổi, nếu không xảy ra biến đổi khác trước nó.

**Công thức trên chỉ mô tả một thay đổi đơn giản với vùng thay thế được biết rõ.** Nếu có nhiều vùng được thay, quy tắc tổng quát là cộng các độ lệch của những lần thay **trước** vị trí mục tiêu; nếu phép biến đổi xóa, thay hoặc tái sắp xếp chính mục tiêu, không thể luôn xác định một chỉ số mới duy nhất bằng cách cộng độ lệch.

Với normalization Unicode, chuyển hoa/thường phụ thuộc ngữ cảnh, xử lý regex hay thay thế có nhiều điểm khớp, tự “cộng một độ lệch chung” thường không đủ. Cần xác định lại vị trí trên văn bản đầu ra hoặc giữ một bản đồ ánh xạ sinh ra cùng phép biến đổi.

## 5. Trường hợp 1: đổi chữ hoa có thể mở rộng `ß` thành `SS`

Trên Java 17:

```java
String original = "Stra\u00DFe|END";
int oldPos = original.indexOf('|'); // 6

String upper = original.toUpperCase(java.util.Locale.ROOT);

System.out.println(original.length()); // 10
System.out.println(upper.length());    // 11
System.out.println(oldPos);            // 6
System.out.println(upper.indexOf('|'));// 7
System.out.println(upper.charAt(6));   // E
```

Giải thích chỉ số:

| Chuỗi | Nội dung | Chỉ số của `|` |
| --- | --- | ---: |
| Gốc | `Straße|END` | 6 |
| Sau biến đổi | `STRASSE|END` | 7 |

Vùng `"Straße"` dài 6 code unit, còn `"STRASSE"` dài 7. Thêm một code unit trước `|` đã làm tất cả vị trí theo sau lệch thêm một đơn vị.

Điểm cần lưu ý:
- `toUpperCase(Locale.ROOT)` thực hiện chuyển chữ hoa theo quy tắc không phụ thuộc locale mặc định, nhưng **không bảo đảm giữ nguyên độ dài**.
- `toLowerCase(Locale)` cũng có thể phụ thuộc locale, ngữ cảnh và biến đổi độ dài. Ví dụ một số phép biến đổi chữ `İ` (Latin capital I with dot) có thể tạo ra nhiều code point với locale thích hợp.
- Việc chuyển hoa/thường không tạo một **bản đồ vị trí gốc → kết quả** cho người gọi; chỉ biết văn bản kết quả chưa đủ để khôi phục mọi quan hệ khi ký tự bị mở rộng hoặc gộp.

## 6. Trường hợp 2: Unicode normalization có thể rút ngắn hoặc kéo dài

Unicode có nhiều cách mã hóa tương đương về mặt chuẩn tắc. Chữ `é` có thể là:
- Một code point dựng sẵn `U+00E9`.
- Hai code point `U+0065` (`e`) và `U+0301` (combining acute accent).

`Normalizer.Form.NFC` có thể ghép chúng thành một code point; `Normalizer.Form.NFD` có thể tách ra.

```java
import java.text.Normalizer;

String decomposed = "Cafe\u0301|OK";
int separatorBefore = decomposed.indexOf('|'); // 5

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(decomposed.length());     // 8
System.out.println(normalized.length());     // 7
System.out.println(separatorBefore);         // 5
System.out.println(normalized.indexOf('|'));  // 4
System.out.println(normalized.charAt(5));     // O
```

Dấu `|` ở chỉ số 5 trên chuỗi gốc chuyển về chỉ số 4 trên chuỗi NFC. Nếu lấy vùng phía sau dấu bằng `substring(separatorBefore + 1)` trên chuỗi đã chuẩn hóa, bạn sẽ bỏ mất ký tự đầu tiên của vùng cần lấy.

**Normalization không đồng nghĩa xóa dấu**. NFC giữ ý nghĩa Unicode chuẩn tắc; nó chỉ đổi cách biểu diễn. `Normalizer.Form.NFKC/NFKD` còn có phép chuẩn hóa tương thích, có thể tác động đến những khác biệt ký tự khác. Hãy chọn dạng chuẩn hóa theo yêu cầu dữ liệu và chấp nhận rằng độ dài có thể thay đổi.

## 7. Trường hợp 3: thay thế và thay đổi độ dài UTF-16 khi có emoji

`String` dùng UTF-16, vì vậy thay một ký tự BMP bằng một code point ngoài BMP có thể tăng `length()` dù số code point không đổi.

```java
String source = "A\uD83D\uDE80B"; // A🚀B
int oldB = source.indexOf("B");   // 3

String changed = source.replace("A", "AA");

System.out.println(source.length());  // 4
System.out.println(changed.length()); // 5
System.out.println(oldB);             // 3
System.out.println(changed.indexOf("B")); // 4
```

Chính ký tự `🚀` chiếm **hai** code unit, và phép thay thế thêm một `A` trước `B`, nên `B` dịch từ chỉ số 3 sang 4.

Một ví dụ khác, thay `"A"` bằng `"🚀"`:

```java
String source = "AB";
String changed = source.replace("A", "\uD83D\uDE80");

System.out.println(source.length());          // 2
System.out.println(changed.length());         // 3
System.out.println(source.codePointCount(0, source.length()));   // 2
System.out.println(changed.codePointCount(0, changed.length())); // 2
```

Ở đây **số code point vẫn bằng 2**, còn độ dài UTF-16 tăng từ 2 lên 3. Vì vậy, chỉ nhìn số code point trước/sau chưa đủ để tính độ lệch của các API nhận chỉ số `char`.

## 8. Chương trình Java 17+ chạy độc lập

Lưu nội dung sau thành file `StringIndexAfterTransformDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class StringIndexAfterTransformDemo {
    public static void main(String[] args) {
        String original = "Stra\u00DFe|END";
        int oldSeparator = original.indexOf('|');
        String upper = original.toUpperCase(Locale.ROOT);

        System.out.println("original = " + original);
        System.out.println("upper = " + upper);
        System.out.println("original length = " + original.length());
        System.out.println("upper length = " + upper.length());
        System.out.println("old separator = " + oldSeparator);
        System.out.println("new separator = " + upper.indexOf('|'));
        System.out.println("char at old index = "
                + upper.charAt(oldSeparator));
        System.out.println("correct right part = "
                + upper.substring(upper.indexOf('|') + 1));

        String decomposed = "Cafe\u0301|OK";
        String nfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFD-like length = "
                + decomposed.length());
        System.out.println("NFC length = " + nfc.length());
        System.out.println("old NFC separator = "
                + decomposed.indexOf('|'));
        System.out.println("new NFC separator = " + nfc.indexOf('|'));

        String emoji = "A\uD83D\uDE80B";
        String inserted = emoji.replace("A", "AA");

        System.out.println("emoji old length = " + emoji.length());
        System.out.println("emoji new length = " + inserted.length());
        System.out.println("emoji old B index = " + emoji.indexOf("B"));
        System.out.println("emoji new B index = " + inserted.indexOf("B"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StringIndexAfterTransformDemo.java
java StringIndexAfterTransformDemo
```

Kết quả:

```text
original = Straße|END
upper = STRASSE|END
original length = 10
upper length = 11
old separator = 6
new separator = 7
char at old index = E
correct right part = END
NFD-like length = 8
NFC length = 7
old NFC separator = 5
new NFC separator = 4
emoji old length = 4
emoji new length = 5
emoji old B index = 3
emoji new B index = 4
```

Bản `String` cũ không hề bị chỉnh sửa. Hai biến tham chiếu `original`/`upper`, `decomposed`/`nfc`, `emoji`/`inserted` lần lượt chứa các phiên bản khác nhau của nội dung. Mọi chỉ số phải được giải thích **trên đúng phiên bản chuỗi sinh ra nó**.

## 9. Sai lầm phổ biến: dùng lại `substring`, `Matcher` hoặc vị trí con trỏ cũ

Giả sử phân tích chuỗi thành hai phần qua dấu `|`:

```java
String input = "Stra\u00DFe|END";
int cut = input.indexOf('|');

String upper = input.toUpperCase(java.util.Locale.ROOT);

// SAI: cut được tính trên input, không phải upper.
String wrong = upper.substring(cut + 1);

// ĐÚNG: tìm lại ranh giới trên chuỗi kết quả.
int newCut = upper.indexOf('|');
String correct = upper.substring(newCut + 1);
```

`wrong` ở ví dụ này trả `"|END"`, còn `correct` trả `"END"`, bởi sau khi mở rộng `ß`, vị trí của dấu phân cách đã tăng lên 1.

Các nơi khác cũng có thể mắc lỗi này:
- Lưu `start`/`end` từ `Matcher.find()` trên chuỗi gốc, rồi dùng các chỉ số đó để cắt chuỗi sau khi `replaceAll` hoặc normalize.
- Lưu vị trí dấu phân cách bằng `indexOf`, rồi gọi `stripLeading` khiến tiền tố bị xóa.
- Lưu điểm bắt đầu vùng được bôi chọn (selection) trong một editor, rồi chuẩn hóa hoặc thay thế văn bản trước vùng đó.
- Lưu ranh giới cắt theo `length()` gốc rồi chuyển chữ hoa/thường toàn chuỗi.
- Ghi chỉ số UTF-16 trong một hệ thống nhưng truyền nó như chỉ số code point cho API khác.

**Nguyên tắc:** Một chỉ số không tự tồn tại độc lập; nó luôn đi kèm **phiên bản văn bản + đơn vị chỉ số + ý nghĩa của vị trí**.

## 10. Các cách xử lý an toàn

### Cách A — Biến đổi trước, tìm chỉ số sau

Khi có thể xác định ranh giới bằng dấu phân cách, mẫu hoặc token sau biến đổi, hãy xử lý chuỗi trước rồi tìm vị trí trong chính kết quả:

```java
String normalized = java.text.Normalizer.normalize(
        input, java.text.Normalizer.Form.NFC);
int separator = normalized.indexOf('|');

if (separator < 0) {
    throw new IllegalArgumentException("Missing separator");
}
String right = normalized.substring(separator + 1);
```

Cách này đơn giản, nhưng cần kiểm tra nếu phép biến đổi có thể thay đổi hoặc loại bỏ dấu phân cách. Với dấu/từ khóa xuất hiện nhiều lần, `indexOf` không tự cho biết đâu là occurrence ban đầu cần theo dõi; hãy dùng cấu trúc dữ liệu ổn định hơn (ID, vị trí token trong cây cú pháp, hoặc offset map).

### Cách B — Trích xuất vùng có ý nghĩa trước rồi biến đổi từng vùng

Khi các phần văn bản được tách bằng một ranh giới rõ ràng, thường thuận tiện hơn nếu bạn **chia trước**:

```java
import java.util.Locale;

String input = "Stra\u00DFe|END";
int separator = input.indexOf('|');

String left = input.substring(0, separator)
                   .toUpperCase(Locale.ROOT);
String right = input.substring(separator + 1)
                    .toUpperCase(Locale.ROOT);

String result = left + "|" + right;
System.out.println(result); // STRASSE|END
```

Lúc này, ranh giới được xác định trên chuỗi gốc đúng nơi nó có ý nghĩa; phép biến đổi sau đó diễn ra riêng trong mỗi thành phần. Tất nhiên, nếu bạn vẫn cần trỏ tới ký tự bên trong `left` hoặc `right` sau biến đổi, vị trí bên trong thành phần đó vẫn phải được tính lại.

### Cách C — Ánh xạ vị trí khi tự kiểm soát các phép chỉnh sửa

Nếu bạn chủ động thực hiện **một lần** thay đoạn `[start, end)` của chuỗi gốc bằng `replacement`, có thể xác định độ lệch của các vị trí nằm **sau** đoạn thay:

```java
int oldLength = end - start;
int newLength = replacement.length();
int delta = newLength - oldLength;

// Áp dụng cho một vị trí p nằm SAU hoặc TẠI end,
// và chỉ khi đây là phép sửa duy nhất ảnh hưởng trước p.
int newPosition = p + delta;
```

Nếu `p < start`, vị trí không đổi (trong trường hợp không có sửa nào khác). Nếu `p` nằm **bên trong** vùng bị thay, không có quy tắc chung để biết “ký tự tương ứng” ở kết quả; phải định nghĩa chính sách con trỏ (ví dụ gắn về đầu hoặc cuối đoạn thay) tùy ứng dụng.

Với nhiều thay đổi, hãy tạo mapping từ chuỗi sửa đổi đã thực hiện: lưu mỗi khoảng nguồn, khoảng đích và độ lệch lũy kế. Các phép biến đổi không bảo toàn một-một, như chuẩn hóa hoặc case mapping, cần quy tắc mapping riêng cho vị trí trong phần bị gộp/mở rộng. Không nên suy luận mapping bằng một tỷ lệ độ dài chung.

### Cách D — Nếu sửa nhiều vùng ở vị trí gốc, cân nhắc sửa từ phải sang trái

Khi có nhiều **vùng không giao nhau được xác định trước trên chuỗi gốc**, thực hiện các phép thay thế từ vị trí lớn xuống nhỏ có thể giữ cho các vị trí gốc **ở bên trái** chưa bị dịch.

Ví dụ:

```java
StringBuilder text = new StringBuilder("abcd");

// Vùng cuối trước, rồi mới vùng đầu; hai vùng không giao nhau.
text.replace(2, 4, "XYZ"); // abXYZ
text.replace(0, 2, "P");   // PXYZ

System.out.println(text); // PXYZ
```

Đây là một kỹ thuật hữu ích với nhiều lần sửa do ứng dụng tự xác định vị trí; nó **không tự ánh xạ** con trỏ hoặc token xuyên qua một phép chuẩn hóa Unicode toàn chuỗi, và không áp dụng bừa bãi khi các vùng chồng lấn nhau.

## 11. `offsetByCodePoints` giúp đổi đơn vị, không giúp ánh xạ qua phép biến đổi

API `String.offsetByCodePoints(int index, int codePointOffset)` nhận **chỉ số UTF-16** trong **một chuỗi cụ thể**, di chuyển theo số code point và trả về chỉ số UTF-16 trong **cùng chuỗi đó**.

Ví dụ:

```java
String text = "A\uD83D\uDE80B"; // A🚀B
int beforeRocket = text.offsetByCodePoints(0, 1);
int afterRocket = text.offsetByCodePoints(beforeRocket, 1);

System.out.println(beforeRocket); // 1
System.out.println(afterRocket);  // 3
System.out.println(text.substring(beforeRocket, afterRocket)); // 🚀
```

Phương thức này rất hữu ích khi cắt chuỗi theo số code point. Nhưng nếu bạn đã chuyển đổi `text` thành một `String` khác có độ dài/nội dung thay đổi, không thể truyền các chỉ số cũ vào chuỗi mới và giả định chúng còn đúng.

Một số phép biến đổi có thể làm thay đổi **ngay cả số code point** (`ß` → `SS`, `e + ◌́` → `é`). Vì vậy đổi sang chỉ số code point **không loại bỏ nhu cầu ánh xạ giữa phiên bản gốc và phiên bản kết quả**.

## 12. Kiểm thử khi một ứng dụng lưu vị trí văn bản

Đối với chức năng soạn thảo, highlight, chú thích, phân tích cú pháp hoặc trích xuất dữ liệu, nên kiểm thử tối thiểu các nhóm sau:

| Dữ liệu kiểm thử | Điều cần kiểm chứng |
| --- | --- |
| ASCII đơn giản, không đổi độ dài | Các chỉ số vẫn đúng khi phép biến đổi thật sự bảo toàn đơn vị và thứ tự. |
| Ký tự có case expansion như `ß` | Chỉ số sau vùng mở rộng tăng. |
| Chuỗi gồm dấu kết hợp + NFC/NFD | Chỉ số có thể giảm/tăng, một vùng cũ có thể không còn tương ứng từng `char`. |
| Ký tự ngoài BMP như `🚀` | Chỉ số UTF-16 khác số code point. |
| Chuỗi có khoảng trắng ở đầu + `stripLeading` | Mọi vị trí phía sau phần bị xóa cần tính lại trên chuỗi mới. |
| Thay regex nhiều lần, thay đổi độ dài ở nhiều điểm | Một độ lệch duy nhất thường không đủ; cần tái tính/mapping có hệ thống. |
| Dấu phân cách hoặc token bị thay/xóa | Không thể chỉ tìm lại bằng chuỗi cũ; cần chiến lược nhận diện token. |
| Chỉ số nằm trong vùng bị thay hoặc ngay tại ranh giới | Chính sách neo vị trí phải được định nghĩa rõ. |

Khi lưu chỉ số ở API hoặc database, hãy ghi rõ đơn vị (**UTF-16 code unit**, **code point** hoặc **grapheme cluster**) và phiên bản văn bản mà vị trí đó tham chiếu. Chỉ số có thể vẫn nằm trong phạm vi hợp lệ nhưng biểu thị một phần hoàn toàn khác của chuỗi sau biến đổi.

## 13. Các lỗi thường gặp

**Lỗi 1 — “`String` bất biến nên chỉ số không đổi.”** Đối tượng gốc bất biến; chuỗi sau phép biến đổi là một giá trị khác. Chỉ số cũ áp dụng cho đối tượng gốc.

**Lỗi 2 — “Chuyển hoa/thường luôn đổi một ký tự thành một ký tự.”** Một số ánh xạ Unicode như `ß` → `SS` thay đổi số code point và `char`. Không dùng giả định này cho văn bản quốc tế.

**Lỗi 3 — “Chuẩn hóa Unicode không thay đổi độ dài.”** NFC/NFD có thể ghép/tách code point, nên vị trí ranh giới thay đổi dù ý nghĩa văn bản tương đương.

**Lỗi 4 — “Số code point không đổi thì chỉ số UTF-16 không đổi.”** Thay `"A"` bằng `"🚀"` giữ một code point nhưng thêm một UTF-16 code unit.

**Lỗi 5 — “Nếu `index < newString.length()` thì dùng được.”** Kiểm tra giới hạn chỉ xác nhận một vị trí hợp lệ về mặt số học; không bảo đảm nó còn trỏ tới token/ký tự cũ.

**Lỗi 6 — “Tìm lại bằng `indexOf` luôn ánh xạ chính xác vị trí gốc.”** Nếu token xuất hiện nhiều lần, bị thay đổi hoặc bị xóa trong phép biến đổi, cần nhận diện ổn định hoặc mapping được tạo cùng thao tác.

**Lỗi 7 — “`offsetByCodePoints` chuyển chỉ số từ chuỗi cũ sang chuỗi mới.”** API này chỉ di chuyển theo code point **trong cùng chuỗi**.

## 14. Bài tập tự kiểm tra

### Bài 1 — Vị trí dấu phân cách sau case mapping

```java
String a = "Stra\u00DFe|OK";
int p = a.indexOf('|');
String b = a.toUpperCase(java.util.Locale.ROOT);
```

Hỏi `p` và `b.indexOf('|')`?

**Đáp án:** `p == 6`, `b.indexOf('|') == 7`. Chuỗi `"Straße"` đổi thành `"STRASSE"` dài hơn một UTF-16 code unit.

### Bài 2 — Vị trí dấu phân cách sau NFC

```java
String a = "e\u0301|B";
String b = java.text.Normalizer.normalize(
        a, java.text.Normalizer.Form.NFC);
```

Hỏi dấu `|` ở vị trí nào trước và sau?

**Đáp án:** Trước ở chỉ số `2` (hai code point `e` và dấu sắc), sau ở chỉ số `1` (chữ `é` dựng sẵn).

### Bài 3 — Chỉ số code point và UTF-16

```java
String before = "AB";
String after = before.replace("A", "\uD83D\uDE80");
```

Hỏi `after.length()` và số code point?

**Đáp án:** `after.length() == 3`, còn `after.codePointCount(0, after.length()) == 2`. `🚀` là một code point nhưng hai `char`.

### Bài 4 — Sửa lỗi dùng offset cũ

```java
String input = "Stra\u00DFe|END";
int oldPos = input.indexOf('|');
String upper = input.toUpperCase(java.util.Locale.ROOT);

// Cần lấy "END", nhưng code sau lấy sai:
String result = upper.substring(oldPos + 1);
```

**Cách sửa:** Tính `int newPos = upper.indexOf('|');` rồi `String result = upper.substring(newPos + 1);`. Nếu có nhiều dấu phân cách, hãy xác định rõ dấu cần dùng để tránh chỉ chọn nhầm occurrence.

### Bài 5 — Có thể cập nhật một offset bằng chênh lệch `length()` không?

**Đáp án:** Chỉ trong điều kiện cụ thể: bạn biết các vùng sửa và chúng nằm trước vị trí cần cập nhật, không thay/xóa chính vị trí đó. Với nhiều vùng sửa hoặc biến đổi Unicode toàn chuỗi, phải theo dõi mapping hoặc xác định lại vị trí trên kết quả; `newLength - oldLength` toàn chuỗi không đủ để ánh xạ tùy ý.

## Tài liệu tham khảo

- [Java SE 17 — `String` API: `length`, `substring`, `replace`, `toUpperCase`, `offsetByCodePoints`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Normalizer`: NFC, NFD, NFKC, NFKD](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 17 — `Character`: Unicode code point và surrogate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
