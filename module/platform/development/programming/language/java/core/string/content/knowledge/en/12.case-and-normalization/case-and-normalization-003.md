# Trường hợp chữ I của tiếng Thổ Nhĩ Kỳ trong Java

Chuyển chữ hoa/thường tưởng như chỉ cần gọi `toLowerCase()` hoặc `toUpperCase()`. Nhưng tiếng Thổ Nhĩ Kỳ (Turkish) có quy tắc đặc biệt với chữ **I**: chữ **I** không dấu chấm phía trên đi cặp với **ı** thường không dấu chấm; chữ **İ** hoa có dấu chấm đi cặp với **i** thường có dấu chấm. Nếu sử dụng locale không đúng, ứng dụng có thể đổi sai tên người, từ ngữ, khóa tìm kiếm hoặc mã định danh.

Trong Java, ba câu hỏi khác nhau phải được tách bạch:

1. **Chuyển chữ cho người đọc thuộc ngôn ngữ nào?** Dùng `String.toLowerCase(Locale)` / `toUpperCase(Locale)` với locale phù hợp.
2. **Chuẩn hóa chuỗi kỹ thuật không phụ thuộc ngôn ngữ?** Dùng chính sách xác định, thường là `Locale.ROOT` với dữ liệu Unicode nếu quy ước cho phép, hoặc quy tắc ASCII tường minh nếu giao thức chỉ định ASCII.
3. **Hai chuỗi có bằng nhau theo quy tắc nào?** `equals()`, `equalsIgnoreCase()` và so sánh theo ngôn ngữ có hợp đồng khác nhau. Đặc biệt, `equalsIgnoreCase()` **không thực hiện phép so sánh riêng cho tiếng Thổ Nhĩ Kỳ**.

## 1. Bốn chữ I/i rất dễ nhầm

| Ký tự | Unicode code point | Tên Unicode | Nhận biết |
| --- | --- | --- | --- |
| `I` | `U+0049` | LATIN CAPITAL LETTER I | Hoa **không có chấm** |
| `i` | `U+0069` | LATIN SMALL LETTER I | Thường **có chấm** |
| `İ` | `U+0130` | LATIN CAPITAL LETTER I WITH DOT ABOVE | Hoa **có chấm** |
| `ı` | `U+0131` | LATIN SMALL LETTER DOTLESS I | Thường **không có chấm** |

Quy tắc cặp chữ trong tiếng Thổ Nhĩ Kỳ:

~~~text
I  <-->  ı     (không có dấu chấm)
İ  <-->  i     (có dấu chấm)
~~~

Trong tiếng Anh, nhiều người quen với cặp `I ↔ i`. Áp dụng thói quen đó cho mọi ngôn ngữ sẽ làm sai chữ Thổ Nhĩ Kỳ.

Ví dụ từ `"istanbul"` được viết hoa theo locale Thổ Nhĩ Kỳ thành `"İSTANBUL"`, có chữ `İ` ở đầu. Tương tự, chữ `I` trong một từ tiếng Thổ Nhĩ Kỳ khi chuyển về chữ thường sẽ thành `ı`, không phải `i`. Không nên dựa vào hình dáng ký tự khi đọc log; có thể in code point dưới dạng `U+....` để đối chiếu.

## 2. Java toLowerCase/toUpperCase chịu ảnh hưởng của Locale

Java có hai nhóm overload chính:

~~~java
text.toLowerCase();
text.toUpperCase();

text.toLowerCase(locale);
text.toUpperCase(locale);
~~~

Đây là **các lời gọi minh họa**, giả sử `text` là `String` và `locale` là `java.util.Locale`.

- **Không truyền đối số:** `toLowerCase()` và `toUpperCase()` dùng **locale mặc định** của JVM, tức `Locale.getDefault()`. Kết quả có thể khác khi ứng dụng chạy ở máy hoặc cấu hình locale khác.
- **Truyền locale rõ ràng:** `toLowerCase(Locale)` và `toUpperCase(Locale)` dùng quy tắc hoa/thường theo locale được chỉ định. Đây là cách nên dùng khi yêu cầu kết quả nhất quán.
- `Locale.forLanguageTag("tr-TR")` tạo locale tiếng Thổ Nhĩ Kỳ dùng trong ví dụ. `Locale.ROOT` là locale trung lập ngôn ngữ, hữu ích cho nhiều thao tác xử lý chuỗi kỹ thuật.

Ví dụ:

~~~java
import java.util.Locale;

// Đoạn lệnh bên trong một phương thức Java:
Locale tr = Locale.forLanguageTag("tr-TR");
Locale root = Locale.ROOT;

System.out.println("TITLE".toLowerCase(root)); // title
System.out.println("TITLE".toLowerCase(tr));   // tıtle
System.out.println("istanbul".toUpperCase(root)); // ISTANBUL
System.out.println("istanbul".toUpperCase(tr));   // İSTANBUL
~~~

Bốn dòng `println` tạo kết quả minh họa như trong chú thích. Trong `tıtle`, ký tự thứ hai là `ı (U+0131)`. Trong `İSTANBUL`, ký tự đầu là `İ (U+0130)`.

**Không nên dùng `toLowerCase()` không đối số để sinh khóa kỹ thuật** khi cần kết quả thống nhất ở mọi nơi. Nếu JVM có locale Thổ Nhĩ Kỳ, `"TITLE".toLowerCase()` có thể thành `"tıtle"`; ở môi trường tiếng Anh, nó có thể thành `"title"`. Hai chuỗi khác nhau theo `equals()`, và mã băm `hashCode()` có thể khác. Điều này có thể ảnh hưởng đến tên khóa, định tuyến, phân quyền hoặc tra cứu nếu thiết kế phụ thuộc vào một quy tắc chữ thường cố định.

### Bảng chuyển đổi code point dưới hai locale

Các giá trị sau được xác minh bằng Java:

| Ký tự đầu vào | `toLowerCase(Locale.ROOT)` | `toLowerCase(tr-TR)` | `toUpperCase(Locale.ROOT)` | `toUpperCase(tr-TR)` |
| --- | --- | --- | --- | --- |
| `I (U+0049)` | `i (U+0069)` | `ı (U+0131)` | `I (U+0049)` | `I (U+0049)` |
| `i (U+0069)` | `i (U+0069)` | `i (U+0069)` | `I (U+0049)` | `İ (U+0130)` |
| `İ (U+0130)` | **`i + U+0307`** (2 code point) | `i (U+0069)` | `İ (U+0130)` | `İ (U+0130)` |
| `ı (U+0131)` | `ı (U+0131)` | `ı (U+0131)` | `I (U+0049)` | `I (U+0049)` |

Điểm tinh tế: `"İ".toLowerCase(Locale.ROOT)` không chỉ ra một `i` đơn lẻ; kết quả là **`i` rồi đến dấu chấm kết hợp `U+0307`**. Vì vậy chuyển chữ hoa/thường ở cấp `String` có thể **thay đổi số code point và `length()`**. Không được mặc định chuyển đổi 1 ký tự đầu vào luôn tương ứng 1 ký tự đầu ra.

## 3. Ví dụ Java 17+ chạy độc lập và xem chính xác code point

Để không phụ thuộc font của console (chữ `I/i/İ/ı` có thể khó phân biệt), chương trình in các Unicode code point dưới dạng hex. Lưu vào tệp **TurkishIDemo.java**:

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class TurkishIDemo {
    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        Locale root = Locale.ROOT;
        Locale tr = Locale.forLanguageTag("tr-TR");

        String[] letters = {"I", "i", "\u0130", "\u0131"};
        for (String letter : letters) {
            System.out.printf(
                    "%s | ROOT lower=%s | TR lower=%s | ROOT upper=%s | TR upper=%s%n",
                    codePoints(letter),
                    codePoints(letter.toLowerCase(root)),
                    codePoints(letter.toLowerCase(tr)),
                    codePoints(letter.toUpperCase(root)),
                    codePoints(letter.toUpperCase(tr)));
        }

        System.out.println("TITLE ROOT lower = "
                + codePoints("TITLE".toLowerCase(root)));
        System.out.println("TITLE TR lower = "
                + codePoints("TITLE".toLowerCase(tr)));
        System.out.println("istanbul ROOT upper = "
                + codePoints("istanbul".toUpperCase(root)));
        System.out.println("istanbul TR upper = "
                + codePoints("istanbul".toUpperCase(tr)));

        System.out.println("I ignoreCase i = "
                + "I".equalsIgnoreCase("i"));
        System.out.println("I ignoreCase dotless = "
                + "I".equalsIgnoreCase("\u0131"));
        System.out.println("I ignoreCase dottedCapital = "
                + "I".equalsIgnoreCase("\u0130"));

        System.out.println("TR lower I equals lower i = "
                + "I".toLowerCase(tr).equals("i".toLowerCase(tr)));
        System.out.println("TR lower I equals lower dotless = "
                + "I".toLowerCase(tr).equals("\u0131".toLowerCase(tr)));
        System.out.println("ROOT lower dotted capital length = "
                + "\u0130".toLowerCase(root).length());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TurkishIDemo.java
java TurkishIDemo
~~~

**Stdout:**

~~~text
U+0049 | ROOT lower=U+0069 | TR lower=U+0131 | ROOT upper=U+0049 | TR upper=U+0049
U+0069 | ROOT lower=U+0069 | TR lower=U+0069 | ROOT upper=U+0049 | TR upper=U+0130
U+0130 | ROOT lower=U+0069 U+0307 | TR lower=U+0069 | ROOT upper=U+0130 | TR upper=U+0130
U+0131 | ROOT lower=U+0131 | TR lower=U+0131 | ROOT upper=U+0049 | TR upper=U+0049
TITLE ROOT lower = U+0074 U+0069 U+0074 U+006C U+0065
TITLE TR lower = U+0074 U+0131 U+0074 U+006C U+0065
istanbul ROOT upper = U+0049 U+0053 U+0054 U+0041 U+004E U+0042 U+0055 U+004C
istanbul TR upper = U+0130 U+0053 U+0054 U+0041 U+004E U+0042 U+0055 U+004C
I ignoreCase i = true
I ignoreCase dotless = true
I ignoreCase dottedCapital = true
TR lower I equals lower i = false
TR lower I equals lower dotless = true
ROOT lower dotted capital length = 2
~~~

Những kết quả cốt lõi:

1. Dòng `U+0049` chứng minh `I` thành `i` với `ROOT` nhưng thành `ı` với `tr-TR`.
2. Dòng `U+0069` chứng minh `i` thành `I` với `ROOT` nhưng thành `İ` với `tr-TR`.
3. Dòng `U+0130` chứng minh phép chuyển thành chữ thường có thể tạo **hai code point** khi dùng `ROOT`.
4. Kết quả `equalsIgnoreCase()` là `true` cho cả ba so sánh có `I`, trong khi quy tắc chữ thường tiếng Thổ Nhĩ Kỳ phân biệt `I` với `i`.
5. Vì vậy, một chức năng muốn so sánh “bằng nhau không phân biệt hoa/thường theo tiếng Thổ Nhĩ Kỳ” **không thể mặc định dùng `equalsIgnoreCase()`**.

Mã nguồn sử dụng escape `\u0130` và `\u0131` để thể hiện hai ký tự đặc biệt mà không phụ thuộc khả năng gõ phím hoặc font; giá trị thực vẫn là hai Unicode code point tương ứng.

## 4. Vì sao equalsIgnoreCase() có thể gây bất ngờ?

`String.equalsIgnoreCase()` là phép so sánh nội dung **không phân biệt hoa/thường theo quy tắc Java**, không nhận `Locale` và không dùng quy tắc Thổ Nhĩ Kỳ khi so sánh. Theo hợp đồng của API, các phép chuyển chữ đơn giản của `Character` được dùng để xác định ký tự có tương đương khi bỏ qua hoa/thường hay không.

Trong Java hiện đại, cả bốn giá trị `I`, `i`, `İ`, `ı` có thể được `equalsIgnoreCase()` coi là bằng nhau từng cặp. Điều đó **khác** cặp chữ đúng của tiếng Thổ Nhĩ Kỳ:

~~~text
Theo tiếng Thổ Nhĩ Kỳ:
    I  ↔  ı
    İ  ↔  i

Với String.equalsIgnoreCase:
    I, i, İ, ı có thể được coi tương đương,
    nên phép so sánh này không tách hai cặp của tiếng Thổ Nhĩ Kỳ.
~~~

Ví dụ:

~~~java
Locale tr = Locale.forLanguageTag("tr-TR");

System.out.println("I".equalsIgnoreCase("i")); // true
System.out.println("I".toLowerCase(tr)
        .equals("i".toLowerCase(tr)));         // false
~~~

Đây là **đoạn mã minh họa**, cần đặt trong một phương thức có import `Locale`.

Không có mâu thuẫn: **mỗi API có một hợp đồng khác nhau**. `equalsIgnoreCase()` không hứa cung cấp Unicode full case folding theo từng ngôn ngữ; `toLowerCase(tr)` được thiết kế cho việc chuyển chữ theo quy tắc locale được truyền.

### Phân biệt thêm với equals(), compareToIgnoreCase()

- `equals()` so sánh dãy code unit UTF-16 **nguyên văn**. `"I".equals("i")` trả về `false`.
- `equalsIgnoreCase()` bỏ qua hoa/thường theo quy tắc Java, **không locale-sensitive**.
- `compareToIgnoreCase()` và `String.CASE_INSENSITIVE_ORDER` dùng thứ tự so sánh không phân biệt hoa/thường theo Java, **không thay thế phép sắp xếp/so khớp tiếng Thổ Nhĩ Kỳ**.
- `java.text.Collator` cung cấp cơ chế so sánh văn bản theo locale, bao gồm quy tắc sắp xếp (*collation*) của ngôn ngữ. Tuy nhiên, việc chọn mức độ so sánh `PRIMARY`, `SECONDARY` hay `TERTIARY` còn ảnh hưởng tới dấu và những khác biệt khác; không nên tự coi mọi cấu hình Collator là tương đương chính xác với “bỏ qua hoa/thường”.

Nếu yêu cầu sản phẩm là so sánh hoặc sắp xếp tên tiếng Thổ Nhĩ Kỳ, cần quy định rõ có phân biệt dấu, chuẩn hóa Unicode và phương thức collation nào phù hợp rồi **kiểm thử trên văn bản bản địa**.

## 5. Chuyển chữ cho nội dung hiển thị và cho khóa kỹ thuật

### Trường hợp A: văn bản dành cho người dùng tiếng Thổ Nhĩ Kỳ

Khi hiển thị văn bản, tạo nhãn hoặc biến đổi dữ liệu theo chính tả tiếng Thổ Nhĩ Kỳ, chọn locale rõ ràng:

~~~java
Locale turkish = Locale.forLanguageTag("tr-TR");
String upper = "istanbul".toUpperCase(turkish); // "İSTANBUL"
String lower = "I".toLowerCase(turkish);        // "ı"
~~~

Đây là **đoạn mã minh họa**, cần đặt trong phương thức Java. Đặt locale từ cấu hình ngôn ngữ thật của dữ liệu hay người dùng, không suy ra locale chỉ từ vị trí đặt máy chủ.

### Trường hợp B: khóa kỹ thuật, từ khóa giao thức hoặc tên trường không phụ thuộc locale

Ví dụ một giao thức định nghĩa các từ khóa `"TITLE"` và `"title"` tương đương bất kể ngôn ngữ người dùng. Nếu chuẩn hóa bằng locale mặc định của JVM, một máy cấu hình `tr-TR` có thể tạo `"tıtle"` và không khớp khóa `"title"`.

Giải pháp thường dùng:

~~~java
Locale root = Locale.ROOT;
String key = "TITLE".toLowerCase(root);
System.out.println(key.equals("title")); // true
~~~

**Lưu ý quan trọng:** `Locale.ROOT` là lựa chọn không phụ thuộc ngôn ngữ, nhưng nó **không tự giải quyết mọi quy tắc định danh Unicode hoặc mọi loại case folding**. Nếu chuẩn/giao thức chỉ chấp nhận ASCII, có thể tốt hơn nếu **kiểm tra dữ liệu chỉ chứa ASCII** và thực hiện quy tắc hoa/thường ASCII được đặc tả. Với tên miền, địa chỉ email, username, mã định danh bảo mật, định dạng giao thức và quy tắc xác thực, hãy tuân theo **chuẩn riêng của lĩnh vực đó**; không mặc định một lần `toLowerCase(Locale.ROOT)` là đủ để đồng nhất mọi dữ liệu Unicode.

### Trường hợp C: khóa tra cứu được định nghĩa “không phân biệt hoa/thường theo tiếng Thổ Nhĩ Kỳ”

Một cách tiếp cận đơn giản khi quy tắc ứng dụng **thật sự** là so sánh theo kết quả lowercasing Thổ Nhĩ Kỳ: tạo khóa chuẩn bằng **cùng locale** trước khi thêm và trước khi tra cứu.

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

// Đoạn mã minh họa bên trong một phương thức:
Locale tr = Locale.forLanguageTag("tr-TR");
Map<String, String> names = new HashMap<>();

names.put("I".toLowerCase(tr), "dotless pair");
names.put("İ".toLowerCase(tr), "dotted pair");

System.out.println(names.get("ı".toLowerCase(tr))); // dotless pair
System.out.println(names.get("i".toLowerCase(tr))); // dotted pair
System.out.println(names.size());                  // 2
~~~

Cách này **phù hợp với chính sách ánh xạ khóa đã định nghĩa**: hai cặp chữ không bị trộn. Nó không phải một định nghĩa tổng quát của mọi quy tắc Unicode hay collation tiếng Thổ Nhĩ Kỳ. Nếu yêu cầu còn có các dạng Unicode chuẩn hóa khác nhau, phải quyết định thêm cách normalize, các trường hợp chữ nhiều code point và chính sách phân biệt dấu trước khi làm khóa.

Không phối hợp kiểu **ghi bằng `toLowerCase(tr)` nhưng tìm bằng `toLowerCase(Locale.ROOT)`**: từ `I` sinh ra hai chuỗi khác nhau `ı` và `i`, dẫn đến tra cứu sai.

## 6. Độ dài và ký tự kết hợp: chữ İ là ví dụ đặc biệt

Để minh họa vì sao chuyển hoa/thường không luôn là phép ánh xạ 1 `char` → 1 `char`:

~~~java
String capitalDottedI = "\u0130";
String lowerRoot = capitalDottedI.toLowerCase(Locale.ROOT);
String lowerTurkish = capitalDottedI.toLowerCase(
        Locale.forLanguageTag("tr-TR"));

System.out.println(capitalDottedI.length()); // 1
System.out.println(lowerRoot.length());      // 2
System.out.println(lowerTurkish.length());   // 1
~~~

Đây là **đoạn mã minh họa** trong phương thức Java. Với `ROOT`, kết quả là `U+0069 U+0307`: chữ `i` rồi dấu chấm kết hợp (*COMBINING DOT ABOVE*). Với `tr-TR`, kết quả là một chữ `i (U+0069)`.

Hệ quả:

- Không cấp phát bộ đệm dựa trên giả định “đổi case không đổi `String.length()`”.
- Không duyệt bằng `charAt(i)` rồi áp dụng một phép đổi chữ đơn giản trên mỗi `char` nếu muốn mô phỏng mọi quy tắc `String.toLowerCase(locale)`. Unicode case mapping có thể phụ thuộc ngữ cảnh, locale và có thể tạo nhiều code point.
- Khi tính vị trí cắt chuỗi sau phép chuyển chữ, không được tự giả định các UTF-16 offset trước và sau chuyển đổi sẽ luôn giữ nguyên.
- **Unicode normalization** (ví dụ `java.text.Normalizer`) và **locale-sensitive case conversion** là hai bước có mục đích khác nhau. Việc chuẩn hóa dạng tổ hợp Unicode không tự thay đổi quy tắc rằng `I` và `i` là hai chữ thuộc hai cặp khác nhau trong tiếng Thổ Nhĩ Kỳ.

### Character.toLowerCase() không thay thế được String.toLowerCase(Locale)

`Character.toLowerCase(char)` / `Character.toLowerCase(int)` thực hiện ánh xạ ký tự ở mức thấp, không nhận locale và không có khả năng trả lại chuỗi nhiều ký tự như `"i\u0307"` từ một lời gọi trả về `char`/`int`. Với dữ liệu dạng một từ hoặc câu, cần chuyển case theo ngôn ngữ, **ưu tiên `String.toLowerCase(Locale)`**.

## 7. Locale mặc định ảnh hưởng thế nào đến ứng dụng?

Xét mã:

~~~java
String command = "QUIT".toLowerCase();
~~~

Khi Java dùng locale mặc định Thổ Nhĩ Kỳ, chữ `I` trong `QUIT` có thể biến thành `ı`, tạo ra `"quıt"` (dotless i). Nếu chương trình tiếp tục so sánh nguyên văn với `"quit"`, phép so sánh có thể thất bại. Đây là lỗi do **phụ thuộc môi trường khi thực hiện chuyển case**, không phải do Unicode hay Java làm hỏng chuỗi.

Tránh sửa toàn bộ trạng thái ứng dụng bằng `Locale.setDefault(...)` chỉ để giải quyết một thao tác chuyển case. Locale mặc định là trạng thái chung của JVM và có thể ảnh hưởng các thành phần khác dùng locale mặc định. **Truyền locale ngay tại lời gọi** khiến hợp đồng rõ hơn và ít gây tác động phụ.

Một số tình huống kiểm tra cần thiết:

| Dữ liệu/ngữ cảnh | Mong muốn | Cách xử lý phù hợp |
| --- | --- | --- |
| Nhãn hoặc từ tiếng Thổ Nhĩ Kỳ | Tuân chính tả `I ↔ ı`, `İ ↔ i` | `toLowerCase(tr)` / `toUpperCase(tr)` |
| Từ khóa phần mềm được đặc tả không phụ thuộc ngôn ngữ | Kết quả ổn định mọi máy | Chính sách kỹ thuật cố định, có thể dùng `Locale.ROOT` khi phù hợp |
| Tìm kiếm không phân biệt hoa/thường trong tiếng Thổ Nhĩ Kỳ | Không gộp sai hai cặp I | Quy tắc so sánh/chuẩn hóa theo locale, hoặc Collator được cấu hình và kiểm thử |
| So sánh nội dung nguyên văn | Phân biệt chính xác dãy UTF-16 | `equals()` |
| Thử nghiệm môi trường | Phát hiện phụ thuộc locale ngầm | Kiểm thử với `en-US`, `tr-TR`, `Locale.ROOT` và các ví dụ I/i/İ/ı |
| Hệ thống có quy định ASCII-only | Tuân đúng tập và quy tắc ASCII | Kiểm tra ASCII, biến đổi theo quy tắc giao thức, không tùy tiện Unicode-fold |

## 8. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `"TITLE".toLowerCase()` để sinh khóa ổn định | Kết quả đổi theo default locale, có thể sinh `tıtle` | Chỉ định chính sách/locale tường minh |
| Coi `I` và `i` là một cặp trong mọi ngôn ngữ | Sai đối với tiếng Thổ Nhĩ Kỳ | Hiểu cả bốn chữ I/i/İ/ı |
| Dùng `equalsIgnoreCase()` cho đối sánh tiếng Thổ Nhĩ Kỳ | Có thể gộp nhầm hai cặp chữ | Dùng cơ chế so sánh theo chính sách ngôn ngữ |
| Cho rằng `Locale.ROOT` là tiếng Thổ Nhĩ Kỳ | ROOT không chứa quy tắc locale Thổ Nhĩ Kỳ | Dùng `Locale.forLanguageTag("tr-TR")` cho tiếng Thổ Nhĩ Kỳ |
| Cho rằng `Locale.ROOT` xử lý mọi vấn đề định danh Unicode | Full Unicode case folding/normalization có nhiều quy tắc | Theo chuẩn dữ liệu và chính sách định danh cụ thể |
| Giả sử `String.toLowerCase()` giữ nguyên độ dài | `İ` chuyển sang ROOT lower thành hai code point | Kiểm tra độ dài và chỉ số sau phép biến đổi |
| Dùng `Character.toLowerCase(char)` để thay mọi trường hợp `String.toLowerCase(locale)` | Mất ngữ cảnh ngôn ngữ và ánh xạ nhiều code point | Dùng API `String` với locale cho văn bản |
| Dùng `==` để so sánh chuỗi sau chuẩn hóa | `==` so sánh danh tính đối tượng | Dùng `equals()` cho giá trị chuỗi |
| Một nơi lưu khóa theo tr-TR, nơi khác tìm theo ROOT | Truy xuất thất bại hoặc trộn quy tắc khóa | Chuẩn hóa và so sánh **nhất quán** |
| Dùng phép chuyển chữ thay cho định nghĩa so sánh tiếng Thổ Nhĩ Kỳ đầy đủ | Có thể bỏ qua collation, normalization, dấu và ngữ cảnh | Định nghĩa tiêu chí rõ và kiểm thử với văn bản thật |

## 9. Checklist trước khi chuyển hoa/thường hoặc so sánh chuỗi

1. **Xác định văn bản thuộc ngôn ngữ nào** và liệu locale của người dùng có liên quan tới phép biến đổi hay không.
2. **Làm rõ mục đích:** hiển thị theo chính tả, sắp xếp tên, tra cứu không phân biệt hoa/thường, hay chuẩn hóa một mã máy đọc.
3. **Chỉ định locale rõ ràng** khi gọi `toLowerCase()` / `toUpperCase()` theo yêu cầu; tránh phụ thuộc default locale khi kết quả cần ổn định.
4. **Với tiếng Thổ Nhĩ Kỳ, thử đủ bốn chữ** `I`, `i`, `İ` và `ı`, cả chữ đơn lẻ và trong từ thực tế.
5. **Không dùng `equalsIgnoreCase()` như một trình đối sánh locale-sensitive**. Xác định rõ quy tắc bằng nhau nào cần được áp dụng.
6. **Không giả định biến đổi 1–1:** `String.toLowerCase(Locale)` có thể tạo nhiều code point, ảnh hưởng chỉ số và độ dài.
7. **Với khóa tra cứu**, áp dụng cùng một quy trình chuẩn hóa/so sánh lúc lưu và lúc tìm; tránh trộn locale giữa hai bước.
8. **Kiểm tra chính sách Unicode:** normalization, full case folding, giới hạn ASCII, xử lý ký tự gần giống nhau, theo đặc tả của ứng dụng.
9. **Tránh thay đổi `Locale.setDefault()` chỉ để sửa một đoạn mã**, vì có thể tác động các phần khác trong JVM.

## 10. Tự kiểm tra

**Câu 1.** Trong tiếng Thổ Nhĩ Kỳ, `I` đổi thành chữ thường nào? `i` đổi thành chữ hoa nào?

**Đáp án:** `I → ı (U+0131)`; `i → İ (U+0130)`.

**Câu 2.** `"TITLE".toLowerCase(Locale.ROOT)` và `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))` có giống nhau không?

**Đáp án:** không. ROOT cho `title`, còn `tr-TR` cho `tıtle`, trong đó chữ thứ hai là dotless `ı`.

**Câu 3.** `"I".equalsIgnoreCase("i")` trả về `true`. Điều đó có chứng minh hai chữ là một cặp hoa/thường đúng trong tiếng Thổ Nhĩ Kỳ không?

**Đáp án:** không. `equalsIgnoreCase()` không dùng locale Thổ Nhĩ Kỳ; theo tiếng Thổ Nhĩ Kỳ, `I` ghép với `ı` và `İ` ghép với `i`.

**Câu 4.** Vì sao `"\u0130".toLowerCase(Locale.ROOT).length() == 2`?

**Đáp án:** kết quả gồm `i (U+0069)` và dấu chấm kết hợp `U+0307`, tức hai UTF-16 code unit. Chuyển case có thể tăng chiều dài chuỗi.

**Câu 5.** Một ứng dụng cần chuẩn hóa từ khóa giao thức như `"QUIT"`, bất kể ngôn ngữ máy chủ. Có nên gọi `"QUIT".toLowerCase()` mà không chỉ định locale không?

**Đáp án:** không. Locale mặc định có thể là tiếng Thổ Nhĩ Kỳ khiến `QUIT` thành `quıt`. Chọn quy tắc kỹ thuật cố định và dùng locale tường minh hoặc thuật toán ASCII theo đúng chuẩn giao thức.

**Câu 6.** Có thể xử lý chính xác mọi loại so sánh văn bản Thổ Nhĩ Kỳ chỉ bằng cách lowercase rồi `equals()` không?

**Đáp án:** không nên khẳng định như vậy. Lowercasing theo locale có thể phù hợp với một **chính sách khóa cụ thể**, nhưng collation, normalization và các mức độ phân biệt dấu có thể yêu cầu công cụ và quy định bổ sung.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toUpperCase(Locale)`, `equalsIgnoreCase()`, `compareToIgnoreCase()`.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, `Locale.forLanguageTag()`, default locale.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): ánh xạ hoa/thường mức ký tự và giới hạn so với ánh xạ chuỗi.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): so sánh văn bản có nhận biết locale.
- [Unicode SpecialCasing.txt](https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt): dữ liệu ánh xạ hoa/thường đặc biệt, bao gồm locale/ngữ cảnh.
