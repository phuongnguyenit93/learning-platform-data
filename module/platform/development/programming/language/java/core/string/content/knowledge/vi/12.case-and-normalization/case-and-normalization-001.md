# `toLowerCase()` và `toUpperCase()` với locale tường minh trong Java

Chuyển một `String` sang chữ thường hoặc chữ hoa là thao tác quen thuộc khi chuẩn bị nội dung hiển thị, so khớp hoặc tạo khóa tìm kiếm. Trong Java, hai lời gọi `text.toLowerCase()` và `text.toUpperCase()` **phụ thuộc vào locale mặc định** của môi trường chạy. Cùng một đầu vào có thể được đổi chữ khác nhau nếu chương trình chạy với ngôn ngữ/khu vực khác.

Để hành vi rõ ràng, hãy ưu tiên overload nhận `Locale` khi yêu cầu đã xác định: `text.toLowerCase(locale)` và `text.toUpperCase(locale)`. Với dữ liệu kỹ thuật không gắn với ngôn ngữ tự nhiên, thường dùng `Locale.ROOT`; với văn bản cần quy tắc của một ngôn ngữ cụ thể, chọn locale tương ứng. Không có một locale đúng cho tất cả dữ liệu.

## 1. Hai nhóm overload và ý nghĩa

Lớp `java.lang.String` cung cấp bốn phương thức:

```java
String toLowerCase()
String toLowerCase(Locale locale)
String toUpperCase()
String toUpperCase(Locale locale)
```

Đây là chữ ký để tham khảo, không phải một lớp Java hoàn chỉnh.

- `toLowerCase()`: chuyển chữ thường theo `Locale.getDefault()` hiện tại.
- `toUpperCase()`: chuyển chữ hoa theo `Locale.getDefault()` hiện tại.
- `toLowerCase(locale)`: dùng quy tắc ánh xạ chữ thường của `locale` đã truyền.
- `toUpperCase(locale)`: dùng quy tắc ánh xạ chữ hoa của `locale` đã truyền.

Các phép chuyển trả về một giá trị `String` tương ứng; chúng **không sửa nội dung** của chuỗi nguồn, vì `String` bất biến. Không phải mọi ký tự đều có phiên bản hoa/thường. Chữ số, phần lớn dấu câu và nhiều ký hiệu giữ nguyên, nhưng một số chữ có cách biến đổi phụ thuộc ngôn ngữ.

Ví dụ cơ bản:

```java
String original = "Java Core";
String lower = original.toLowerCase(Locale.ROOT);
String upper = original.toUpperCase(Locale.ROOT);

// original: "Java Core"
// lower:    "java core"
// upper:    "JAVA CORE"
```

Đoạn này dùng `Locale.ROOT` từ `java.util.Locale` và cần đặt trong một phương thức/lớp có import phù hợp. Hai lời gọi trả về giá trị mới hoặc tham chiếu có nội dung tương ứng; không cần quan tâm kết quả có được cấp phát đối tượng mới trong mọi trường hợp hay không.

## 2. Vì sao gọi không tham số có thể gây hành vi khác nhau?

`toLowerCase()` không tham số tương đương về quy tắc lựa chọn locale với `toLowerCase(Locale.getDefault())`; tương tự đối với `toUpperCase()`. Locale mặc định có thể được JVM xác định từ thiết lập môi trường và có thể bị thay đổi trong quá trình chạy bằng API của `Locale`.

Vì vậy, hai máy có thể xử lý khác nhau một từ chứa chữ `I` dù code ứng dụng giống hệt. Ví dụ nổi tiếng là **tiếng Thổ Nhĩ Kỳ (Turkish)**:

- Trong ngữ cảnh tiếng Anh hoặc ánh xạ trung tính thông dụng: `I` → `i` khi viết thường.
- Trong tiếng Thổ Nhĩ Kỳ: `I` → `ı` (LATIN SMALL LETTER DOTLESS I).
- Ngược lại, tiếng Thổ Nhĩ Kỳ có `i` → `İ` (LATIN CAPITAL LETTER I WITH DOT) khi viết hoa.

Nếu chương trình tạo khóa tra cứu một tên trường kỹ thuật bằng `toLowerCase()` không tham số, kết quả có thể phụ thuộc máy chạy. Điều đó khó kiểm thử và có thể làm sai cách tra cứu hoặc so sánh sau khi chuyển môi trường.

Tệp `ExplicitLocaleDemo.java`:

```java
import java.util.Locale;

public class ExplicitLocaleDemo {
    public static void main(String[] args) {
        String word = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");

        System.out.println("ROOT lower: " +
                word.toLowerCase(Locale.ROOT));
        System.out.println("TR lower: " +
                word.toLowerCase(turkish));
        System.out.println("ROOT upper: " +
                "file".toUpperCase(Locale.ROOT));
        System.out.println("TR upper: " +
                "file".toUpperCase(turkish));
        System.out.println("source: " + word);
    }
}
```

Lưu đúng tên tệp, biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

Đầu ra:

```text
ROOT lower: title
TR lower: tıtle
ROOT upper: FILE
TR upper: FİLE
source: TITLE
```

Kết quả cho thấy chỉ thay `Locale` đã khiến các ký tự `I` và `i` được chuyển khác nhau. Ví dụ không cần thay locale mặc định của máy vì đã truyền locale một cách tường minh, giúp kết quả thử nghiệm rõ ràng hơn.

## 3. Chọn `Locale.ROOT` hay locale của một ngôn ngữ?

### `Locale.ROOT`: quy tắc không gắn với một khu vực/ngôn ngữ cụ thể

`Locale.ROOT` là locale trung tính. Nó hữu ích cho những dữ liệu **do chương trình quy định**, ví dụ mã trạng thái có ký tự Latin cơ bản, tên khóa trong giao thức hoặc chuẩn hóa một nhãn kỹ thuật khi hệ thống quy định so khớp không phụ thuộc thiết lập người dùng.

```java
import java.util.Locale;

String command = "START";
String canonical = command.toLowerCase(Locale.ROOT);
// canonical bằng "start"
```

Điều quan trọng là ***đặc tả dữ liệu***: nếu giao thức quy định mã phải là ASCII hoặc một tập ký tự cố định, bạn vẫn nên xác thực đúng tập ký tự đó trước khi chuẩn hóa. `Locale.ROOT` không tự biến dữ liệu Unicode bất kỳ thành một chuỗi ASCII hợp lệ, và cũng không bảo đảm phép biến đổi là một-một.

Không nên diễn giải `Locale.ROOT` là locale “tốt hơn” đối với mọi tên người, câu chữ hoặc văn bản tự nhiên. Nó chỉ loại bỏ sự phụ thuộc vào **locale mặc định**, chứ không tự giải quyết các yêu cầu ngôn ngữ học.

### Locale tường minh theo ngôn ngữ

Khi kết quả phải phù hợp quy tắc chữ hoa/thường của nội dung/người dùng, chọn locale được định nghĩa trong yêu cầu:

```java
import java.util.Locale;

Locale turkish = Locale.forLanguageTag("tr-TR");
String lowerTurkish = "I".toLowerCase(turkish); // "ı"
String upperTurkish = "i".toUpperCase(turkish); // "İ"
```

Có thể dùng các hằng như `Locale.ENGLISH` cho nội dung tiếng Anh hoặc `Locale.forLanguageTag("vi-VN")` khi chính sách xử lý văn bản thuộc môi trường Việt Nam. Tuy nhiên, **không lấy locale theo nơi đặt máy chủ làm mặc định nghiệp vụ** nếu văn bản của người dùng thực sự thuộc ngôn ngữ khác.

Với mã nhận từ bên ngoài và cần kết quả tái lập, locale phải là **đầu vào có chủ đích** hoặc là một giá trị cố định trong đặc tả ứng dụng. `Locale.getDefault()` chỉ phù hợp nếu mục tiêu thật sự là “làm theo thiết lập ngôn ngữ mặc định hiện tại”.

## 4. Quy tắc chữ I Thổ Nhĩ Kỳ cho thấy khác biệt về locale

Cặp `I ↔ ı` và `İ ↔ i` của tiếng Thổ Nhĩ Kỳ cho thấy **locale làm thay đổi kết quả**, không chỉ thay đổi cách hiển thị. Với `tr-TR`, `"I".toLowerCase(tr)` là `"ı"`; với `Locale.ROOT` là `"i"`. Bài riêng về chữ I Thổ Nhĩ Kỳ phân tích đủ bốn code point và khác biệt với `equalsIgnoreCase()` bằng chương trình in `U+...`.

## 5. Chuyển hoa/thường có thể đổi độ dài

`"Straße".toUpperCase(Locale.ROOT)` cho `"STRASSE"` (6 → 7 `char`), và `"\u0130".toLowerCase(Locale.ROOT)` tạo `"i\u0307"` (1 → 2 `char`). Đây là phép ánh xạ chuỗi Unicode, không phải thay thế độc lập từng `char`.

```java
String before = "Straße";
String upper = before.toUpperCase(java.util.Locale.ROOT);
System.out.println(before.length() + " -> " + upper.length()); // 6 -> 7
System.out.println(before.equals(upper));                      // false
```

Đoạn lệnh đặt trong một phương thức. Hãy tính các chỉ số và giới hạn độ dài trên **kết quả sau biến đổi**, tránh tái sử dụng offset của chuỗi gốc. Bài về độ dài đi sâu vào lỗi offset `Straße`/`STRASSE`.

## 6. Chuyển case không luôn có phép đảo ngược

Nhiều chuỗi đầu vào có thể ánh xạ thành cùng chữ hoa: `"straße".toUpperCase(Locale.ROOT)` và `"STRASSE".toUpperCase(Locale.ROOT)` đều cho `"STRASSE"`. Chuyển chuỗi ấy về chữ thường thành `"strasse"` **không khôi phục** chữ `ß` ban đầu. Nếu cần giữ chính tả người dùng nhập, lưu bản gốc và tạo khóa đã đổi case riêng cho tìm kiếm.

## 7. Cách viết ổn định cho các giá trị kỹ thuật

Giả sử API nhận một trong ba mã chế độ: `READ`, `WRITE`, `ADMIN`. Nếu giao diện muốn cho phép nhập không phân biệt chữ hoa/thường nhưng ngôn ngữ mã là ASCII cố định, hãy kiểm tra chuỗi được chuyển với một locale trung tính:

Tệp `CommandNormalizer.java`:

```java
import java.util.Locale;

public class CommandNormalizer {
    static String normalizeCommand(String input) {
        if (input == null) {
            throw new IllegalArgumentException("command is null");
        }
        String normalized = input.toUpperCase(Locale.ROOT);

        if (!normalized.equals("READ")
                && !normalized.equals("WRITE")
                && !normalized.equals("ADMIN")) {
            throw new IllegalArgumentException("unsupported command");
        }
        return normalized;
    }

    public static void main(String[] args) {
        System.out.println(normalizeCommand("read"));
        System.out.println(normalizeCommand("Write"));
        System.out.println(normalizeCommand("ADMIN"));

        try {
            normalizeCommand("archive");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid command");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CommandNormalizer.java
java CommandNormalizer
```

Kết quả:

```text
READ
WRITE
ADMIN
invalid command
```

`Locale.ROOT` làm phép chuyển không phụ thuộc locale của máy chạy. Tuy nhiên, đây chỉ là một ví dụ chính sách **chấp nhận các mã đã xác định**. Nếu giao thức đòi hỏi đầu vào phải chính xác dạng `READ`/`WRITE`/`ADMIN` và không cho phép dạng khác, đừng tự đổi chữ trước khi xác thực.

Với định danh hệ thống, mã truy cập, khóa ký số, đường dẫn hoặc dữ liệu bảo mật, cần cân nhắc rủi ro nhiều chuỗi khác nhau chuyển thành cùng một dạng và mọi quy tắc xác thực phải được thiết kế thống nhất giữa nơi tạo và nơi kiểm tra giá trị.

## 8. Chọn locale từ yêu cầu sản phẩm thay vì tự đoán

Một hàm có thể nhận rõ `Locale` từ bên gọi:

```java
import java.util.Locale;

public class LocalizedTitle {
    static String uppercaseLabel(String label, Locale locale) {
        if (label == null || locale == null) {
            throw new IllegalArgumentException("label and locale required");
        }
        return label.toUpperCase(locale);
    }

    public static void main(String[] args) {
        String label = "file";
        Locale english = Locale.ENGLISH;
        Locale turkish = Locale.forLanguageTag("tr-TR");

        System.out.println(uppercaseLabel(label, english));
        System.out.println(uppercaseLabel(label, turkish));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocalizedTitle.java
java LocalizedTitle
```

Đầu ra:

```text
FILE
FİLE
```

Trong trường hợp này, trách nhiệm chọn locale thuộc về **ngữ cảnh nghiệp vụ**: người dùng đang nhập một ngôn ngữ nào, nội dung gốc thuộc ngôn ngữ nào, hay ứng dụng yêu cầu biểu diễn trung tính. Locale theo IP của máy chủ, khu vực triển khai hoặc giao diện không luôn tương ứng với ngôn ngữ của nội dung.

Nếu thiếu thông tin về locale mà kết quả phải chính xác cho văn bản tự nhiên, việc **thiết kế rõ một chính sách mặc định** hữu ích hơn là ngầm lệ thuộc `Locale.getDefault()`.

## 9. Đổi case, chuẩn hóa Unicode và collation có mục đích khác nhau

- `toLowerCase(locale)` / `toUpperCase(locale)`: biến đổi chữ theo locale; **không tự** đưa các biểu diễn Unicode tương đương về cùng dạng.
- `Normalizer.normalize(s, Normalizer.Form.NFC)`: chuẩn hóa các biểu diễn Unicode tương đương chuẩn tắc; **không tự** chuyển chữ hoa thành thường.
- `Collator.getInstance(locale)`: so sánh/sắp xếp theo quy tắc ngôn ngữ và cấu hình; **không sửa** nội dung chuỗi.

Ví dụ `"\u00E9".equals("e\u0301")` là `false` dù hai chuỗi có thể nhìn như nhau; chuyển chúng sang lowercase vẫn không bảo đảm `equals`. Nếu bài toán cần canonical equivalence, chuẩn hóa **hai vế** về cùng dạng rồi so sánh. `equalsIgnoreCase()` cũng không nhận locale và không thực hiện toàn bộ Unicode normalization hay so sánh tiếng Thổ Nhĩ Kỳ.

## 10. Xử lý `null` và chuỗi rỗng

Nếu tham chiếu nhận lời gọi là `null`, việc gọi `toLowerCase(...)` hoặc `toUpperCase(...)` gây `NullPointerException`. Nếu tham số `locale` là `null`, overload nhận `Locale` cũng không có một locale hợp lệ để áp dụng và có thể ném `NullPointerException`.

```java
import java.util.Locale;

String value = null;
// value.toLowerCase(Locale.ROOT); // NullPointerException

String safe = value == null
        ? ""
        : value.toLowerCase(Locale.ROOT);
```

Đây là đoạn minh họa bên trong một phương thức; biến `safe` bằng `""` theo **quy ước tự chọn** của ví dụ. Không nên ngầm chuyển mọi `null` thành chuỗi rỗng nếu ứng dụng cần phân biệt “không có giá trị” với “giá trị người dùng nhập là rỗng”.

Với chuỗi nguồn rỗng, việc chuyển hoa/thường vẫn tạo nội dung rỗng:

```java
System.out.println("".toLowerCase(Locale.ROOT).isEmpty()); // true
System.out.println("".toUpperCase(Locale.ROOT).isEmpty()); // true
```

Khoảng trắng cũng không tự động bị cắt bỏ khi đổi chữ. Ví dụ `"  Java  ".toLowerCase(Locale.ROOT)` giữ hai dấu cách đầu/cuối và chỉ đổi các chữ cái thành `"  java  "`. Nếu ứng dụng muốn bỏ whitespace, đó là một bước xử lý khác với chính sách riêng.

## 11. Những lỗi phổ biến

**Lỗi 1 — Dùng `toLowerCase()` không tham số cho khóa hệ thống.** Kết quả phụ thuộc locale mặc định. Nếu đặc tả muốn xử lý trung tính, dùng `toLowerCase(Locale.ROOT)` và kiểm tra tập ký tự hợp lệ.

**Lỗi 2 — Luôn chọn `Locale.ROOT` cho văn bản của mọi ngôn ngữ.** Locale trung tính không thay thế quy tắc chữ của ngôn ngữ thực tế, đặc biệt khi cần xử lý chữ `I/i` trong tiếng Thổ Nhĩ Kỳ.

**Lỗi 3 — Nghĩ chữ hoa/thường luôn có ánh xạ từng ký tự một.** Các ánh xạ đầy đủ có thể tạo thêm code point hoặc phụ thuộc ngữ cảnh, khiến độ dài chuỗi thay đổi.

**Lỗi 4 — Cho rằng có thể đảo lại chuỗi gốc bằng cách đổi hoa rồi thường.** Các giá trị khác nhau có thể quy về cùng một dạng, như `straße` và `STRASSE`; không bảo đảm khôi phục nội dung gốc.

**Lỗi 5 — Tưởng chuyển hoa/thường đồng nghĩa Unicode normalization.** `toLowerCase`/`toUpperCase` không thay thế `Normalizer` và không tự giải quyết khác biệt dạng tiền tổ hợp/dấu kết hợp.

**Lỗi 6 — Coi `equalsIgnoreCase()` là cách so sánh theo locale.** Phương thức không nhận locale; nhu cầu xếp thứ tự hoặc so sánh văn bản tự nhiên theo ngôn ngữ có thể cần `Collator`.

**Lỗi 7 — Đổi chữ ngay trên dữ liệu gốc rồi lưu đè theo thói quen.** Có thể mất định dạng và cách viết người dùng cung cấp, hoặc tạo va chạm định danh. Hãy cân nhắc lưu bản gốc và tạo khóa dẫn xuất nếu chính sách cần.

**Lỗi 8 — Tự suy ra locale từ quốc gia đặt server.** Ngôn ngữ của nội dung có thể không trùng với locale của máy chủ hoặc giao diện; hãy xác định từ yêu cầu nghiệp vụ.

**Lỗi 9 — Tưởng `toUpperCase` sẽ cắt khoảng trắng và sửa mọi khác biệt kiểu chữ.** Phương thức đổi chữ theo quy tắc locale, không phải bộ làm sạch dữ liệu tổng quát.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao nên tránh `"TITLE".toLowerCase()` khi tạo khóa tra cứu kỹ thuật cần giống nhau trên mọi máy?

**Đáp án:** Bởi nó dùng locale mặc định; tại ngữ cảnh tiếng Thổ Nhĩ Kỳ, `I` có thể trở thành `ı` thay vì `i`. Sử dụng một locale tường minh như `Locale.ROOT` giúp xác định quy tắc ngay trong mã.

**Câu 2.** `"file".toUpperCase(Locale.forLanguageTag("tr-TR"))` và `"file".toUpperCase(Locale.ROOT)` khác nhau thế nào?

**Đáp án:** Kết quả tiếng Thổ Nhĩ Kỳ là `"FİLE"` có `İ`, còn `Locale.ROOT` cho `"FILE"` có `I` thông thường.

**Câu 3.** Có thể khẳng định `text.toUpperCase(locale).length() == text.length()` cho mọi `String` không?

**Đáp án:** Không. Unicode có những ánh xạ tăng số code point, ví dụ `ß` → `SS`, làm độ dài UTF-16 có thể thay đổi.

**Câu 4.** Nếu hai chuỗi `"\u00E9"` và `"e\u0301"` cùng hiển thị giống chữ é, đổi cả hai sang chữ thường có bảo đảm `equals()` là `true` không?

**Đáp án:** Không. Chuyển hoa/thường không tự chuẩn hóa hai cách biểu diễn Unicode. Cần xác định chính sách normalization nếu ứng dụng muốn xem chúng là tương đương.

**Câu 5.** Khi hiển thị văn bản do người dùng nhập, có cần lưu đè dạng đã chuyển chữ thường để thuận tiện tìm kiếm không?

**Đáp án:** Không nhất thiết. Có thể giữ nguyên nội dung gốc và tạo một khóa tìm kiếm dẫn xuất với locale/chính sách xác định. Điều này giúp bảo toàn cách viết mà người dùng cung cấp.

**Ghi nhớ:** Hãy chọn locale **một cách tường minh** khi chuyển chữ: dùng `Locale.ROOT` cho quy tắc kỹ thuật trung tính và locale phù hợp khi nội dung cần quy tắc ngôn ngữ. `toLowerCase`/`toUpperCase` xử lý case mapping Unicode, có thể thay đổi độ dài và không phải phép đảo ngược hay Unicode normalization.
