# Chuỗi nhìn giống nhau nhưng khác dãy Unicode code point

## 1. Vì sao đây là một vấn đề thực tế?

Hai chuỗi có thể **trông giống hệt nhau hoặc rất giống nhau trên màn hình** nhưng vẫn chứa **các dãy Unicode code point khác nhau**. Trong Java, điều này ảnh hưởng trực tiếp đến:

- `String.equals(...)`, `compareTo(...)` và `indexOf(...)` khi đối chiếu nội dung.
- Tìm kiếm, lọc trùng, thống kê, sắp xếp và tạo khóa cho `Map`/`Set`.
- Kiểm tra username, mã định danh, tên tệp, địa chỉ hoặc dữ liệu do người dùng nhập.
- Cắt chuỗi, đếm ký tự và xử lý dấu tiếng Việt/emoji.

**Ký tự nhìn thấy** là kết quả của bộ dựng chữ (*text rendering*), font và quy tắc tổ hợp Unicode. **Giá trị `String`** là dãy đơn vị mã UTF-16. Vì vậy, sự giống nhau về hình ảnh không tự động tạo ra bằng nhau về dữ liệu.

Sau bài học, bạn sẽ phân biệt code point, UTF-16 code unit và grapheme cluster; phát hiện khác biệt bằng `codePoints()`; sử dụng bốn dạng Unicode normalization (`NFC`, `NFD`, `NFKC`, `NFKD`) qua `java.text.Normalizer`; và hiểu giới hạn của việc chuẩn hóa khi đối mặt với chữ thuộc các hệ chữ khác nhau, hoa/thường hoặc những ký tự vô hình.

## 2. Phân biệt ba khái niệm

**Unicode code point:** giá trị số như `U+0061` (Latin `a`), `U+00E9` (`é`), `U+0301` (dấu sắc kết hợp) hoặc `U+1F600` (emoji 😀).

**UTF-16 code unit:** đơn vị 16 bit mà `char` của Java lưu. Một code point thuộc Basic Multilingual Plane (BMP) thường chiếm một code unit; code point supplementary như `U+1F600` cần hai code unit tạo thành *surrogate pair*.

**Grapheme cluster:** đơn vị văn bản mà người dùng thường nhận thức như một ký tự. Một grapheme cluster có thể chứa nhiều code point, ví dụ chữ cái kèm dấu kết hợp hoặc một emoji được tạo từ nhiều code point và ký tự nối.

| Văn bản nhìn thấy | Dãy code point | Số code point | Số UTF-16 code unit |
| --- | --- | ---: | ---: |
| `A` | `U+0041` | 1 | 1 |
| `é` (dạng dựng sẵn) | `U+00E9` | 1 | 1 |
| `é` (chữ `e` + dấu sắc kết hợp) | `U+0065 U+0301` | 2 | 2 |
| `😀` | `U+1F600` | 1 | 2 |

**Lưu ý khi đọc bảng:** `é` ở hàng thứ hai và tổ hợp `e` + `U+0301` ở hàng thứ ba thường hiển thị gần như nhau. Khả năng hiển thị chính xác phụ thuộc font, phần mềm dựng chữ và môi trường.

Trong Java:

~~~java
String composed = "caf\u00E9";  // café: ký tự é dựng sẵn U+00E9
String decomposed = "cafe\u0301"; // cafe + dấu sắc kết hợp U+0301

System.out.println(composed.length());  // 4 UTF-16 code units
System.out.println(decomposed.length()); // 5 UTF-16 code units
System.out.println(composed.equals(decomposed)); // false
~~~

Hai chuỗi gần như có cùng hình ảnh nhưng khác dãy dữ liệu. `String.length()` và `equals` đang làm việc đúng theo hợp đồng API.

## 3. Khác dãy code point, nhìn giống: ví dụ `café`

Có hai biểu diễn thường gặp của chữ `é`:

1. **Precomposed:** một code point `U+00E9`, tên Unicode là *LATIN SMALL LETTER E WITH ACUTE*.
2. **Decomposed:** code point `U+0065` (*LATIN SMALL LETTER E*) đi cùng `U+0301` (*COMBINING ACUTE ACCENT*).

Tương ứng:

~~~text
Cách 1: "café"
U+0063 U+0061 U+0066 U+00E9

Cách 2: "cafe" + U+0301
U+0063 U+0061 U+0066 U+0065 U+0301
~~~

Cả hai có thể hiển thị thành chữ `café`. Nhưng:

~~~java
String a = "caf\u00E9";
String b = "cafe\u0301";

System.out.println(a.equals(b));    // false
System.out.println(a.indexOf(b));   // -1
System.out.println(a.length());     // 4
System.out.println(b.length());     // 5
~~~

Đây là sự khác biệt **canonical representation**, thuộc nhóm mà chuẩn hóa Unicode có thể giải quyết. Đừng kết luận một bên “sai Unicode”: cả hai là các dãy được Unicode cho phép. Muốn ứng dụng coi chúng như nhau, hãy định nghĩa chính sách **canonical normalization** trước khi so sánh.

### Việc viết `\uXXXX` trong mã nguồn có ảnh hưởng không?

Trong tệp `.java`, `\u00E9` là một Unicode escape của **mã nguồn**, được trình biên dịch xử lý trước bước nhận diện literal chuỗi. Nếu tệp nguồn trực tiếp chứa `é` và được đọc đúng encoding, cả hai cách viết có thể dẫn đến **cùng code point**.

Sự khác biệt quan trọng ở đây là **`U+00E9` so với `U+0065 U+0301`**, không phải “dùng escape hay gõ ký tự trực tiếp”. Tương tự, một chuỗi nhận từ file/HTTP/database có thể mang dạng chuẩn hóa khác mà ứng dụng không nhận thấy bằng mắt.

## 4. `String.equals` so sánh giá trị, không so sánh hình ảnh

`String.equals(Object)` trả `true` khi các chuỗi chứa cùng **thứ tự đơn vị mã UTF-16**; nó không tự:

- Chuẩn hóa Unicode theo NFC/NFD/NFKC/NFKD.
- Bỏ qua chữ hoa hoặc chữ thường.
- Bỏ dấu tiếng Việt.
- Loại ký tự zero-width hoặc variation selector.
- Nhận biết hai glyph nhìn giống nhau thuộc các hệ chữ khác nhau.
- Sử dụng phép so khớp theo ngôn ngữ hoặc thiết lập locale.

Ví dụ:

~~~java
String first = "caf\u00E9";
String second = "cafe\u0301";

boolean equalRaw = first.equals(second); // false
~~~

`==` lại có nghĩa **so identity tham chiếu** và càng không phù hợp để so sánh nội dung. Chuyển `==` thành `equals` chỉ giải quyết bài toán **identity vs value**; vấn đề canonical equivalence vẫn đòi hỏi bước chuẩn hóa theo chính sách ứng dụng.

Đối với `HashMap` và `HashSet`, `String.hashCode()` cũng dựa vào giá trị chuỗi. Hai cách biểu diễn `café` có thể trở thành **hai khóa khác nhau** nếu không được chuẩn hóa trước khi nhập vào cấu trúc dữ liệu.

## 5. Dùng normalization để xác định hai dãy có tương đương hay không

Khi hai chuỗi giống nhau nhưng `equals` là `false`, hãy thử **cả hai phía** với cùng một dạng:

```java
String a = "caf\u00E9";
String b = "cafe\u0301";
System.out.println(a.equals(b)); // false
System.out.println(java.text.Normalizer.normalize(a, java.text.Normalizer.Form.NFC)
        .equals(java.text.Normalizer.normalize(b, java.text.Normalizer.Form.NFC))); // true
```

`NFC/NFD` dùng **tương đương chuẩn tắc** (ví dụ `é` và `e + ◌́`), còn `NFKC/NFKD` xét thêm **tương đương tương thích** (ví dụ `ﬃ` và `ffi`). Bài này tập trung **chẩn đoán sự khác nhau**; bài `Normalizer` trình bày sâu bốn dạng và chính sách chọn dạng.

Nếu hai chuỗi **vẫn khác nhau** sau NFKC, chúng không nhất thiết sai Unicode: chữ Latin `a` (`U+0061`) và chữ Cyrillic `а` (`U+0430`) nhìn giống nhưng khác code point. Normalization không phải công cụ nhận diện tất cả confusable; cần xem code point, hệ chữ và mục đích so sánh.

## 6. Ví dụ Java 17+ đầy đủ: in code point và kiểm tra các trường hợp

Tạo tệp **`UnicodeLookalikeDemo.java`** với nội dung sau:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class UnicodeLookalikeDemo {
    private static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("composed=" + points(composed));
        System.out.println("decomposed=" + points(decomposed));
        System.out.println("rawEquals=" + composed.equals(decomposed));
        System.out.println("rawLengths=" + composed.length() + "/" + decomposed.length());
        System.out.println("codePoints=" + composed.codePointCount(0, composed.length())
                + "/" + decomposed.codePointCount(0, decomposed.length()));

        String nfc1 = Normalizer.normalize(composed, Normalizer.Form.NFC);
        String nfc2 = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("nfcEquals=" + nfc1.equals(nfc2));
        System.out.println("nfcPoints=" + points(nfc2));
        System.out.println("nfdEquals="
                + Normalizer.normalize(composed, Normalizer.Form.NFD)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFD)));

        String ligature = "\uFB03";
        System.out.println("ligature=" + points(ligature));
        System.out.println("nfcLigatureEqualsFfi="
                + Normalizer.normalize(ligature, Normalizer.Form.NFC).equals("ffi"));
        System.out.println("nfkcLigatureEqualsFfi="
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC).equals("ffi"));
        System.out.println("fullwidthNfkc=" + points(
                Normalizer.normalize("\uFF21", Normalizer.Form.NFKC)));

        String latinA = "a";
        String cyrillicA = "\u0430";
        System.out.println("lookalikeRawEqual=" + latinA.equals(cyrillicA));
        System.out.println("lookalikeNfkcEqual="
                + Normalizer.normalize(latinA, Normalizer.Form.NFKC)
                .equals(Normalizer.normalize(cyrillicA, Normalizer.Form.NFKC)));
        System.out.println("lookalikePoints=" + points(latinA) + " / " + points(cyrillicA));

        String upperDottedI = "\u0130";
        System.out.println("rootLower=" + points(upperDottedI.toLowerCase(Locale.ROOT)));
        System.out.println("turkishLower=" + points(upperDottedI.toLowerCase(
                Locale.forLanguageTag("tr"))));
        System.out.println("caseStillDifferent=" + "Java".equals("java"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeLookalikeDemo.java
java UnicodeLookalikeDemo
~~~

Kết quả `stdout` đã được đối chiếu bằng trình biên dịch Java và JVM:

~~~text
composed=U+0063 U+0061 U+0066 U+00E9
decomposed=U+0063 U+0061 U+0066 U+0065 U+0301
rawEquals=false
rawLengths=4/5
codePoints=4/5
nfcEquals=true
nfcPoints=U+0063 U+0061 U+0066 U+00E9
nfdEquals=true
ligature=U+FB03
nfcLigatureEqualsFfi=false
nfkcLigatureEqualsFfi=true
fullwidthNfkc=U+0041
lookalikeRawEqual=false
lookalikeNfkcEqual=false
lookalikePoints=U+0061 / U+0430
rootLower=U+0069 U+0307
turkishLower=U+0069
caseStillDifferent=false
~~~

**Ý nghĩa các nhóm kết quả:**

1. `composed` và `decomposed` khác độ dài và khác dãy code point nên `equals` trả `false`. Sau chuẩn hóa `NFC` hoặc `NFD` theo cùng dạng, chúng bằng nhau.
2. `NFC` không biến ligature `ﬃ` thành ba chữ `ffi`, còn `NFKC` thì có thể; `NFKC` cũng chuyển fullwidth `Ａ` thành `A`.
3. Chữ `a` Latin (`U+0061`) và chữ `а` Cyrillic (`U+0430`) có thể trông giống nhau nhưng `NFKC` vẫn **không** biến chúng thành cùng một code point.
4. Đổi chữ hoa/chữ thường là một phép biến đổi **khác với normalization**. Ký tự `İ` (Latin Capital I With Dot Above, `U+0130`) viết thường theo `Locale.ROOT` trở thành hai code point `U+0069 U+0307`; theo locale Thổ Nhĩ Kỳ (`tr`) thành một code point `U+0069`.

Hàm `points` dùng `String.codePoints()`, vì thế có thể in đầy đủ code point supplementary dưới dạng `U+1F600`, không chia thành hai ký tự surrogate như khi lặp theo `charAt`.

## 7. Một nhóm khác: chữ khác hệ chữ nhưng gần giống nhau

Không phải mọi cặp nhìn giống nhau đều tương đương canonical hay compatibility. Ví dụ:

| Ký tự | Hệ chữ | Code point |
| --- | --- | --- |
| `a` | Latin small letter a | `U+0061` |
| `а` | Cyrillic small letter a | `U+0430` |
| `A` | Latin capital letter A | `U+0041` |
| `Α` | Greek capital letter Alpha | `U+0391` |
| `О` | Cyrillic capital letter O | `U+041E` |
| `O` | Latin capital letter O | `U+004F` |

Các ký tự đó có thể có nét chữ tương tự, tùy font. Tuy nhiên, chúng là **code point khác nhau** trong các hệ chữ khác nhau. `Normalizer.normalize(..., NFKC)` không được thiết kế để giải quyết toàn bộ hiện tượng chữ gần giống (*confusable characters*, *homoglyphs*).

Ví dụ:

~~~java
String latin = "a";          // U+0061
String cyrillic = "\u0430"; // U+0430

System.out.println(latin.equals(cyrillic)); // false
System.out.println(
    Normalizer.normalize(latin, Normalizer.Form.NFKC).equals(
        Normalizer.normalize(cyrillic, Normalizer.Form.NFKC)
    )
); // false
~~~

Đây là rủi ro khi hệ thống cho phép tạo username/identifier “nhìn giống nhau”. Hai tài khoản có tên hiển thị gần như nhau vẫn có thể có dãy Unicode khác nhau.

**Phân biệt mục tiêu:** canonical normalization giúp đồng nhất một số cách viết tương đương của *cùng văn bản*. Chính sách chống giả mạo tên định danh cần thêm quy tắc hệ chữ, kiểm tra ký tự gây nhầm lẫn và quy trình xử lý confusables theo chuẩn như Unicode Technical Standard #39. Không dùng `NFKC` đơn lẻ như một “bộ chống giả mạo” hoàn chỉnh.

## 8. Ký tự kết hợp, zero-width, variation selector và emoji

Hai chuỗi không chỉ khác nhau bởi dấu dựng sẵn hay chữ ở các hệ chữ khác nhau. Các **code point ảnh hưởng đến hiển thị** cũng có thể gây nhầm lẫn:

- **Combining mark:** dấu kết hợp như `U+0301` nối với chữ đứng trước để tạo một grapheme cluster. Chuỗi có nhiều code point nhưng có thể xuất hiện thành một chữ có dấu.
- **Zero-width joiner (ZWJ, `U+200D`):** tham gia một số chuỗi emoji và quy tắc nối ký tự; có thể không hiển thị như một ký tự độc lập.
- **Variation selector:** ví dụ `U+FE0F` có thể yêu cầu cách trình bày dạng emoji ở những chuỗi hỗ trợ. Sự hiện diện/thiếu nó khiến dãy code point khác nhau dù các phần mềm hiển thị có thể làm kết quả trông tương tự.
- **Ký tự điều khiển hoặc định dạng vô hình:** có thể ảnh hưởng khoảng cách, thứ tự hiển thị, hướng chữ hoặc so khớp, tùy từng ký tự và môi trường.

Chẳng hạn, hai chuỗi sau có giá trị khác nhau:

~~~java
String plain = "\u2764";        // U+2764, HEAVY BLACK HEART
String emojiStyle = "\u2764\uFE0F"; // U+2764 + VARIATION SELECTOR-16

System.out.println(plain.equals(emojiStyle)); // false
System.out.println(plain.codePointCount(0, plain.length())); // 1
System.out.println(emojiStyle.codePointCount(0, emojiStyle.length())); // 2
~~~

Tùy font và nền tảng, chúng có thể đều hiển thị như trái tim hoặc có hai cách trình bày khác nhau. Không thể đánh giá `String` chỉ bằng ảnh chụp màn hình.

Các phép chuẩn hóa `NFC`/`NFD` không có mục đích xóa tùy tiện ZWJ, variation selector hay các ký tự định dạng khác. **Không tự xóa các code point vô hình** chỉ vì chúng không dễ thấy: nhiều code point trong số đó có vai trò chính đáng đối với ngôn ngữ và emoji. Hãy xác định quy tắc xử lý đúng theo loại trường dữ liệu.

## 9. Hoa/thường và locale là vấn đề riêng với chuẩn hóa

Trong nhóm kiến thức **hoa thường và chuẩn hóa**, cần phân biệt ít nhất ba cách đối chiếu:

1. **Code-unit exact equality:** `a.equals(b)`; không chuẩn hóa, không bỏ qua hoa/thường.
2. **Canonical-normalized equality:** `Normalizer.normalize(a, NFC).equals(Normalizer.normalize(b, NFC))`; vẫn phân biệt hoa/thường.
3. **So sánh không phân biệt hoa/thường hoặc theo quy tắc ngôn ngữ:** cần quyết định đúng API và locale, chẳng hạn `equalsIgnoreCase` cho một số bài toán đơn giản hoặc `Collator` theo ngôn ngữ, và có thể kết hợp normalization khi hợp đồng yêu cầu.

Ví dụ chữ `İ` (`U+0130`) trong chương trình ở phần 6 cho thấy một chuyển đổi chữ thường có thể trả **một hoặc nhiều code point** và phụ thuộc locale. Với một số ngôn ngữ, chọn locale không đúng dẫn đến sai nghĩa; với các khóa kỹ thuật không phụ thuộc ngôn ngữ, `Locale.ROOT` có thể thích hợp hơn locale máy chạy, nhưng điều đó **không tự giải quyết mọi yêu cầu Unicode case folding**.

Không nên mặc định rằng `equalsIgnoreCase` luôn xem tất cả các chuỗi tương đương về mặt ngôn ngữ hoặc về canonical normalization là bằng nhau. Tương tự, `Collator` phục vụ **so sánh văn bản theo locale** và có cấu hình phân rã/mức độ so sánh; lựa chọn đúng tùy mục tiêu, không phải một phép thay thế vô điều kiện cho `equals`.

Lưu ý: thao tác đổi hoa/thường hoặc chuẩn hóa **có thể thay đổi độ dài và chỉ số UTF-16**. Nếu đã tìm một vị trí trong chuỗi trước biến đổi, không tự áp dụng index đó lên chuỗi sau biến đổi.

## 10. Quy trình so sánh dữ liệu đáng tin cậy

Giả sử nghiệp vụ quy định hai chuỗi được xem là giống nhau nếu **canonical equivalent**, bất kể được nhập ở dạng dựng sẵn hay phân rã. Có thể viết:

~~~java
import java.text.Normalizer;
import java.util.Objects;

public class CanonicalComparison {
    static String nfc(String value) {
        return Normalizer.normalize(
                Objects.requireNonNull(value, "value"),
                Normalizer.Form.NFC);
    }

    static boolean sameCanonicalText(String left, String right) {
        return nfc(left).equals(nfc(right));
    }

    public static void main(String[] args) {
        System.out.println(sameCanonicalText("caf\u00E9", "cafe\u0301"));
    }
}
~~~

Khi biên dịch và chạy class này, chương trình in `true`. Phần xử lý `null` được định nghĩa rõ bằng `Objects.requireNonNull`; nếu nghiệp vụ coi null là một giá trị đặc biệt, bạn cần sửa hợp đồng kiểm tra cho phù hợp.

Nếu dùng chuỗi làm **khóa tra cứu**:

~~~java
// Snippet minh họa: map là Map<String, Integer> đã được tạo.
map.put(nfc(userInput), 1);
Integer value = map.get(nfc(query));
~~~

Đây là snippet minh họa, không tự chạy độc lập. Chuẩn hóa thống nhất **khi ghi và khi đọc** để cùng một dạng canonical mang về một key. Nếu lưu cả dạng gốc để hiển thị, tách biệt **original value** và **normalized lookup key**. Điều này cho phép giữ nguyên cách người dùng nhập và vẫn có thể so khớp theo quy tắc xác định.

### Chính sách chuẩn hóa cần trả lời rõ

| Loại dữ liệu | Hướng xử lý cần cân nhắc |
| --- | --- |
| Nội dung hiển thị tự do | Giữ bản gốc; chỉ chuẩn hóa nếu có lý do kỹ thuật/nghiệp vụ |
| Tên sản phẩm, từ khóa tìm kiếm | Quy định chuẩn hóa và xử lý hoa/thường, dấu theo ngôn ngữ; chỉ số tìm kiếm xây trên cùng chính sách |
| Username/mã định danh | Xác định tập ký tự, chuẩn hóa, case rules, kiểm tra confusables và uniqueness; không chỉ dựa vào hình ảnh |
| Dữ liệu có chữ kiểu mẫu hoặc ký hiệu học thuật | Thận trọng với `NFKC`/`NFKD` vì có thể làm mất phân biệt compatibility |
| Văn bản đa ngôn ngữ | Chọn chính sách phù hợp ngôn ngữ; không đồng nhất mọi quy tắc hoa/thường và collation |

Một chiến lược đơn giản cho canonical equality là chọn `NFC` và áp dụng nhất quán. Nhưng **không có một dạng chuẩn hóa tối ưu cho mọi hệ thống**: mục đích sử dụng, khả năng truy vết dữ liệu gốc và chính sách định danh mới quyết định.

## 11. Kiểm tra dãy code point khi hai chuỗi “nhìn y như nhau”

Khi xảy ra lỗi so sánh, đừng bắt đầu bằng việc đổi font rồi đoán. Hãy kiểm tra **độ dài, code point và dạng normalization**:

~~~java
String text = "cafe\u0301";

System.out.println(text.length());
System.out.println(text.codePointCount(0, text.length()));
text.codePoints().forEach(cp -> System.out.printf("U+%04X%n", cp));
~~~

Kết quả:

~~~text
5
5
U+0063
U+0061
U+0066
U+0065
U+0301
~~~

Mỗi code point bổ sung như `U+1F600` xuất hiện thành **một** giá trị `int` khi dùng `codePoints()`; nếu duyệt bằng `charAt`, nó xuất hiện thành hai `char` surrogate. Vì vậy `codePoints()` hữu ích hơn khi cần chẩn đoán vấn đề Unicode ở mức code point.

Một quy trình debug có thể gồm:

1. In code point bằng dạng `U+XXXX` cho **cả hai** chuỗi.
2. So `length()`, `codePointCount(...)` và `equals(...)`, xem khác biệt nằm ở đâu.
3. Thử chuẩn hóa cả hai về `NFC` để biết có cùng canonical form không; nếu cần nghiên cứu compatibility, thử `NFKC` **chỉ cho mục đích chẩn đoán**, tránh áp đặt chính sách biến đổi mới lên dữ liệu sản xuất.
4. Nếu vẫn khác, kiểm tra hệ chữ, dấu kết hợp, variation selector, ZWJ và ký tự định dạng; với identifiers, áp dụng kiểm tra confusable theo đặc tả riêng.
5. Xác định quy tắc ứng dụng mong muốn: *nội dung y hệt*, *canonical equivalent*, *không phân biệt hoa/thường*, *ngang nhau theo locale*, hay *trông tương tự*. Đây là các yêu cầu khác nhau.

Không sử dụng code point log chứa dữ liệu nhạy cảm trong môi trường sản xuất nếu không có kiểm soát phù hợp; khi debug, giới hạn dữ liệu được ghi theo nhu cầu thực tế.

## 12. Những lỗi thường gặp

1. **Cho rằng hai chữ nhìn giống nhau thì `equals` phải trả true.** `equals` so sánh dữ liệu, không so ảnh glyph.
2. **Cho rằng hai cách viết `café` khác nhau là một bên sai Unicode.** Cả dạng dựng sẵn lẫn dạng chữ cơ sở + dấu kết hợp đều hợp lệ; quyết định canonical equality do nghiệp vụ quy định.
3. **Nhầm `String.length()` là số ký tự nhìn thấy.** Nó đếm UTF-16 code units; `codePointCount` cũng chưa đếm grapheme clusters.
4. **Dùng `==` để so sánh nội dung.** `==` chỉ so identity; `equals` là phép so sánh giá trị, sau bước chuẩn hóa nếu cần.
5. **Chuẩn hóa một bên mà không chuẩn hóa bên còn lại.** Khi mục tiêu là canonical equality, dùng cùng `Normalizer.Form` cho cả hai.
6. **Dùng NFKC như cách sửa mọi chuỗi nhìn giống nhau.** NFKC không hợp nhất tất cả chữ Latin/Cyrillic/Greek giống nét; nó cũng có thể làm mất các khác biệt compatibility.
7. **Bỏ qua locale khi đổi hoa/thường.** Ký tự `İ` cho thấy phép lowercasing có thể cho các kết quả khác nhau theo locale và làm đổi số code point.
8. **Tùy tiện xóa dấu kết hợp, zero-width hoặc variation selector.** Có thể phá hỏng nội dung hợp lệ, đặc biệt trong tiếng Việt, văn bản đa ngôn ngữ và emoji.
9. **Dùng index cũ sau khi chuẩn hóa.** Vì normalization có thể đổi độ dài code unit, các vị trí `substring`/`charAt` thuộc chuỗi trước chuẩn hóa không luôn dùng được trên chuỗi sau.
10. **Chỉ chuẩn hóa khi truy vấn mà không chuẩn hóa khi lưu khóa.** Một map hoặc index tìm kiếm sẽ không tra đúng nếu hai bên dùng hai chính sách biểu diễn khác nhau.
11. **Tự xây cơ chế chống giả mạo bằng vài thay thế ký tự.** Confusable handling là vấn đề riêng; cần chính sách identifier và công cụ phù hợp.

## 13. Bài tập tự kiểm tra

**Câu 1.** Tại sao `"caf\u00E9".equals("cafe\u0301")` trả `false`?

**Đáp án:** vế trái có `U+00E9`, vế phải có `U+0065 U+0301`; hai dãy code point và UTF-16 code unit khác nhau dù hiển thị tương đương canonical.

**Câu 2.** Biến đổi thế nào để so sánh canonical equivalence?

**Đáp án:** chuẩn hóa **cả hai** về cùng dạng `NFC` hoặc `NFD` rồi gọi `equals`.

**Câu 3.** `NFC` có đổi `ﬃ` thành `ffi` không? `NFKC` thì sao?

**Đáp án:** `NFC` không; `NFKC` thực hiện compatibility decomposition và có thể đổi ligature `U+FB03` thành ba chữ `ffi`.

**Câu 4.** Vì sao `Normalizer.normalize("a", NFKC)` và `Normalizer.normalize("\u0430", NFKC)` vẫn khác nhau?

**Đáp án:** chúng thuộc hai hệ chữ khác nhau, Latin `U+0061` và Cyrillic `U+0430`. Giống về hình ảnh không có nghĩa tương đương Unicode normalization.

**Câu 5.** `String.length()` có đo được số grapheme cluster không?

**Đáp án:** không. Nó đếm UTF-16 code unit. `codePointCount` đếm code point, vẫn không phải grapheme cluster.

**Câu 6.** Có thể dùng `NFKC` mặc định cho mọi dữ liệu nhập không?

**Đáp án:** không. NFKC có thể gộp những khác biệt compatibility có ý nghĩa; cần lựa chọn theo mục tiêu của trường dữ liệu.

**Câu 7.** Vì sao nên giữ bản gốc khi xây khóa tìm kiếm chuẩn hóa?

**Đáp án:** khóa đã chuẩn hóa giúp tìm kiếm nhất quán, còn bản gốc giữ đúng cách người dùng nhập, hỗ trợ hiển thị và kiểm tra khi cần. Hai vai trò này không nên đánh đồng.

## 14. Tài liệu chuẩn

- [Java SE 17 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): bốn dạng chuẩn hóa và cách sử dụng trong Java.
- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `equals`, `length`, `codePoints`, `codePointCount` và chuyển đổi hoa/thường.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): định nghĩa NFC, NFD, NFKC và NFKD.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): grapheme cluster và phân đoạn văn bản.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): nhận diện các dạng ký tự confusable trong identifier.

**Ghi nhớ:** “nhìn giống” là đặc điểm hiển thị, còn `String` chứa **dãy UTF-16 code unit cụ thể**. Dùng `codePoints()` để xem dữ liệu thật; dùng `Normalizer` khi cần chuẩn hóa canonical/compatibility theo một **chính sách đã xác định**; và xử lý riêng trường hợp chữ gần giống khác hệ chữ, Unicode case rules cùng các grapheme cluster phức tạp.