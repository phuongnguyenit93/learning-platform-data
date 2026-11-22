# CharSequence.compare và thứ tự từ điển trong Java 11+

## 1. Mục tiêu: so sánh chuỗi theo thứ tự nào?

Trong Java, `String`, `StringBuilder`, `StringBuffer` và một số kiểu khác cùng biểu diễn được dãy ký tự thông qua giao diện `CharSequence`. Khi cần xếp thứ tự hoặc tìm xem hai dãy ký tự đứng trước/sau nhau, từ **Java 11** có phương thức tĩnh:

```java
int result = CharSequence.compare(first, second);
```

Phương thức `CharSequence.compare(CharSequence cs1, CharSequence cs2)` so sánh **theo thứ tự từ điển (lexicographical order)** dựa trên từng giá trị `char`. Phương thức vẫn có trong Java hiện đại, có thể dùng khi biên dịch theo Java 11 trở lên.

**Điểm rất quan trọng trong chủ đề Unicode:** đây là phép so sánh **giá trị mã của các đơn vị UTF-16**, không phải cách sắp xếp từ ngữ theo tiếng Việt hay một ngôn ngữ tự nhiên. Muốn sắp xếp tên người, từ có dấu hoặc văn bản theo quy tắc ngôn ngữ, cần chọn giải pháp khác như `java.text.Collator`.

## 2. Kiểu dữ liệu, cú pháp và kết quả trả về

```java
public static int compare(CharSequence cs1, CharSequence cs2)
```

Cả hai đối số đều là `CharSequence`, nên có thể kết hợp các đối tượng khác lớp:

```java
CharSequence left = "Java";
CharSequence right = new StringBuilder("Java");

int result = CharSequence.compare(left, right); // 0
```

Ý nghĩa kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| `< 0` | `cs1` đứng **trước** `cs2` |
| `== 0` | Hai dãy có **cùng độ dài và cùng từng đơn vị `char`** |
| `> 0` | `cs1` đứng **sau** `cs2` |

Đừng dựa vào giả định kết quả luôn là `-1`, `0` hoặc `1`. Hợp đồng của API chỉ đảm bảo **dấu âm / bằng không / dấu dương**. Nếu cần chuẩn hóa thành ba giá trị, dùng `Integer.signum(CharSequence.compare(a, b))`.

Khác với `String.compareTo(String)` (chỉ nhận `String`), `CharSequence.compare` có thể so sánh nội dung giữa `String`, `StringBuilder`, `StringBuffer` hoặc những lớp triển khai `CharSequence` khác. Đây là lý do nó hữu ích khi xử lý nhiều nguồn dữ liệu văn bản.

## 3. Cơ chế so sánh từ điển

Giả sử có hai dãy `a` và `b`. Java so từng vị trí từ trái sang phải:

1. Tìm vị trí đầu tiên `k` mà `a.charAt(k)` và `b.charAt(k)` khác nhau.
2. `char` nào có **giá trị số nhỏ hơn** thì dãy chứa nó đứng trước.
3. Nếu các `char` trong phần chung đều giống nhau, **dãy ngắn hơn đứng trước**; bằng độ dài thì kết quả bằng `0`.

Ví dụ quy tắc, xét dấu kết quả:

| So sánh | Dấu | Giải thích |
| --- | --- | --- |
| `compare("abc", "abd")` | Âm | `'c' < 'd'` ở ký tự khác đầu tiên |
| `compare("cat", "catalog")` | Âm | `"cat"` là tiền tố của `"catalog"` |
| `compare("catalog", "cat")` | Dương | Dãy có cùng tiền tố nhưng dài hơn |
| `compare("Java", new StringBuilder("Java"))` | `0` | Nội dung `char` giống hệt dù khác lớp |
| `compare("Z", "a")` | Âm | `'Z'` (90) nhỏ hơn `'a'` (97) |
| `compare("file10", "file2")` | Âm | Tại ký tự khác đầu tiên, `'1' < '2'` |

Cột thứ tự này dựa vào mã `char`, không tự xử lý thứ tự số tự nhiên: `"file10"` có thể đứng trước `"file2"`. Nó cũng **phân biệt chữ hoa và chữ thường**, không tự bỏ dấu hoặc chuẩn hóa Unicode.

## 4. Ví dụ Java hoàn chỉnh chạy được

Tạo tệp **`CharSequenceCompareDemo.java`** với mã sau. Chương trình không cần thư viện ngoài JDK:

```java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;

public class CharSequenceCompareDemo {
    private static String sign(CharSequence left, CharSequence right) {
        return Integer.toString(Integer.signum(CharSequence.compare(left, right)));
    }

    public static void main(String[] args) {
        CharSequence a = "Java";
        CharSequence b = new StringBuilder("Java");
        System.out.println("same content: " + (CharSequence.compare(a, b) == 0));
        System.out.println("equals objects: " + a.equals(b));
        System.out.println("abc vs abd: " + sign("abc", "abd"));
        System.out.println("cat vs catalog: " + sign("cat", "catalog"));
        System.out.println("Z vs a: " + sign("Z", "a"));
        System.out.println("file10 vs file2: " + sign("file10", "file2"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("raw same: " + (CharSequence.compare(composed, decomposed) == 0));
        System.out.println("NFC same: " + (CharSequence.compare(
                Normalizer.normalize(composed, Normalizer.Form.NFC),
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)) == 0));

        List<CharSequence> words = new ArrayList<>();
        words.add(new StringBuilder("Beta"));
        words.add("Alpha");
        words.add(new StringBuffer("Alpine"));
        words.sort(CharSequence::compare);
        System.out.println("sorted: " + words);

        String emoji = new String(Character.toChars(0x1F600));
        String privateUse = "\uE000";
        System.out.println("emoji UTF16 < U+E000: " + (CharSequence.compare(emoji, privateUse) < 0));
        System.out.println("emoji codePoint > U+E000: " + (emoji.codePointAt(0) > privateUse.codePointAt(0)));
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên (phần code trên tương thích mức Java 11):

```bash
javac --release 11 CharSequenceCompareDemo.java
java CharSequenceCompareDemo
```

**Đầu ra đã kiểm chứng:**

```text
same content: true
equals objects: false
abc vs abd: -1
cat vs catalog: -1
Z vs a: -1
file10 vs file2: -1
raw same: false
NFC same: true
sorted: [Alpha, Alpine, Beta]
emoji UTF16 < U+E000: true
emoji codePoint > U+E000: true
```

Lưu ý `sign(...)` **chủ động chuyển kết quả sang `-1/0/1`** bằng `Integer.signum`; đây không phải cam kết của chính `CharSequence.compare`. Chương trình dùng `List<CharSequence>` để chứng minh có thể sắp xếp các triển khai `CharSequence` khác nhau bằng method reference `CharSequence::compare`.

## 5. `CharSequence.compare` khác `equals` như thế nào?

`CharSequence` **không quy định một hợp đồng `equals` chung** cho mọi lớp triển khai. Ví dụ:

```java
CharSequence a = "Java";
CharSequence b = new StringBuilder("Java");

System.out.println(CharSequence.compare(a, b) == 0); // true
System.out.println(a.equals(b));                      // false
```

`compare(a, b) == 0` nghĩa là **nội dung theo `char` có cùng thứ tự và độ dài**, nhưng `a.equals(b)` có thể khác vì cách định nghĩa `equals` của từng lớp. Với `String`, `equals` đòi đối số là một `String` khác có cùng nội dung; `StringBuilder` không tuân theo tiêu chí so sánh nội dung giống `String`.

Khi chỉ cần biết một `String` có cùng dãy ký tự với một `CharSequence` hay không, cũng có thể dùng:

```java
String s = "Java";
CharSequence builder = new StringBuilder("Java");
boolean sameText = s.contentEquals(builder); // true
```

**Hệ quả thực tế:** đừng dùng `CharSequence::compare` làm comparator của `TreeSet<CharSequence>` hoặc `TreeMap<CharSequence, ...>` nếu ứng dụng cần phân biệt những đối tượng có cùng nội dung nhưng `equals` khác nhau. Các bộ sưu tập có thứ tự có thể coi hai phần tử là cùng khóa khi comparator trả `0`, dù `equals` của chúng trả `false`.

## 6. Unicode: thứ tự UTF-16 không phải thứ tự code point

Trong Java, `CharSequence.length()` đo số **đơn vị `char` 16 bit**, không nhất thiết là số ký tự con người nhận thấy hay số điểm mã Unicode.

Một ký tự nằm ngoài **Basic Multilingual Plane (BMP)** được biểu diễn bằng **cặp surrogate**, tức hai đơn vị `char` UTF-16. Phương thức `CharSequence.compare` làm việc lần lượt với hai đơn vị `char` đó, chứ **không tự gộp cặp surrogate thành một code point rồi mới so sánh**.

Ví dụ trong chương trình:

- `emoji` được tạo từ Unicode code point **U+1F600**; trong UTF-16 nó bắt đầu bằng high surrogate `\uD83D`.
- `privateUse` chứa code point **U+E000**; đây là một ký tự thuộc vùng dùng riêng (private use) trong BMP, chỉ dùng làm ví dụ so sánh số.
- So theo **đơn vị UTF-16**: `\uD83D < \uE000`, nên `CharSequence.compare(emoji, privateUse) < 0` là `true`.
- So theo **giá trị code point**: `0x1F600 > 0xE000`, nên `emoji.codePointAt(0) > privateUse.codePointAt(0)` cũng là `true`.

Không có mâu thuẫn: hai biểu thức đang sử dụng **hai quy tắc thứ tự khác nhau**. Nếu hệ thống yêu cầu thứ tự code point, cần xây dựng comparator đọc `codePoints()` và so từng code point; đừng mặc định `CharSequence.compare` làm điều đó.

Ngoài ra, **grapheme cluster** (ký tự người dùng nhìn thấy) có thể gồm nhiều code point, ví dụ một chữ cái + dấu kết hợp. Thứ tự theo `char`, code point và thứ tự ngôn ngữ là ba vấn đề riêng.

## 7. Unicode normalization: nhìn giống nhau vẫn có thể khác nhau

Một số ký tự Unicode có thể biểu diễn bằng nhiều chuỗi mã tương đương. Ví dụ chữ `é` có thể là:

- `"\u00E9"`: một code point U+00E9 (ký tự dựng sẵn).
- `"e\u0301"`: chữ `e` + dấu sắc kết hợp U+0301 (hai code point).

Hai biểu diễn này có thể trông giống nhau nhưng **khác dãy `char`**, nên `CharSequence.compare` không trả `0` nếu so trực tiếp.

Nếu bài toán cần xem các dạng Unicode tương đương về mặt chuẩn hóa là giống nhau, hãy **chuẩn hóa hai phía về cùng một dạng** như NFC trước khi so sánh:

```java
import java.text.Normalizer;

String left = "\u00E9";
String right = "e\u0301";

String n1 = Normalizer.normalize(left, Normalizer.Form.NFC);
String n2 = Normalizer.normalize(right, Normalizer.Form.NFC);

boolean sameAfterNfc = CharSequence.compare(n1, n2) == 0; // true
```

`Normalizer` là API Java tiêu chuẩn và tiếp tục hữu ích khi dữ liệu đến từ các nguồn khác nhau. **Chuẩn hóa không đồng nghĩa với xóa dấu, đổi hoa/thường hoặc sắp xếp theo ngôn ngữ**. Chọn NFC/NFD/NFKC/NFKD tùy yêu cầu; tránh tùy tiện dùng dạng tương thích NFKC/NFKD cho định danh khi chưa xác định chính sách dữ liệu.

## 8. Khi cần thứ tự tiếng Việt hoặc ngôn ngữ tự nhiên

`CharSequence.compare` không hiểu quy tắc sắp xếp của tiếng Việt: nó không có đối số `Locale`, không xác định thứ tự theo bảng chữ cái bản địa và không tự xử lý dấu hay phân biệt hoa/thường theo ngữ cảnh ngôn ngữ.

Nếu muốn **sắp xếp các từ/người theo locale**, có thể dùng `java.text.Collator`:

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

Collator vietnamese = Collator.getInstance(Locale.forLanguageTag("vi-VN"));

List<String> names = new ArrayList<>(List.of("An", "Ánh", "Ân"));
names.sort(vietnamese);
```

Đây là **đoạn minh họa dùng trong một phương thức**, không phải một chương trình `main` độc lập. `Collator` áp dụng quy tắc so sánh theo locale được hỗ trợ bởi nhà cung cấp dữ liệu locale của môi trường Java; hãy kiểm tra kết quả trên JDK và cấu hình thực tế khi yêu cầu sắp xếp là một phần nghiệp vụ.

Có thể cấu hình mức độ phân biệt của `Collator` bằng `setStrength(...)` (ví dụ `PRIMARY`, `SECONDARY`, `TERTIARY`), nhưng lựa chọn nào đúng phải dựa trên yêu cầu có phân biệt dấu và hoa/thường hay không. Không thay bằng `String.compareToIgnoreCase` nếu yêu cầu thực sự là thứ tự theo ngôn ngữ.

Tóm tắt lựa chọn:

| Nhu cầu | API/cách tiếp cận |
| --- | --- |
| So sánh thứ tự mã `char` giữa các kiểu `CharSequence` | `CharSequence.compare(a, b)` |
| So sánh thứ tự mã `char` giữa hai `String` | `a.compareTo(b)` |
| Kiểm tra hai `CharSequence` có nội dung `char` giống nhau | `CharSequence.compare(a, b) == 0`, hoặc `String.contentEquals(...)` khi có `String` |
| Chuẩn hóa các biểu diễn Unicode tương đương | `Normalizer.normalize(...)` trên cả hai chuỗi |
| Sắp xếp theo ngôn ngữ/locale | `Collator.getInstance(locale).compare(...)` |
| So sánh theo code point hoặc quy tắc tên tệp có số | Comparator tự định nghĩa theo yêu cầu |

## 9. Cách sử dụng an toàn trong xử lý danh sách

Với dữ liệu đã ổn định, `CharSequence::compare` là một comparator ngắn gọn:

```java
List<CharSequence> values = new ArrayList<>();
values.add("apple");
values.add(new StringBuilder("apricot"));
values.add("banana");

values.sort(CharSequence::compare);
```

Khi dữ liệu thay đổi trong lúc sắp xếp, kết quả so sánh có thể không ổn định. Chẳng hạn `StringBuilder` có thể bị sửa sau khi đã được đặt trong tập hợp hoặc bản đồ có thứ tự; việc tra cứu dựa trên comparator khi đó có thể sai kỳ vọng. Với khóa và dữ liệu phải giữ thứ tự ổn định, ưu tiên **chuỗi bất biến `String`** hoặc tạo bản sao `toString()` trước khi sắp xếp.

Nếu một đối số có thể là `null`, đừng gọi so sánh trực tiếp mà chưa xác định quy tắc: một đối số `null` có thể dẫn đến `NullPointerException`. Có thể kiểm tra đầu vào hoặc dùng comparator hỗ trợ null:

```java
import java.util.Comparator;

Comparator<CharSequence> nullsLast =
        Comparator.nullsLast(CharSequence::compare);
```

Đoạn trên đặt `null` ở cuối khi dùng comparator, không thay đổi hành vi của chính `CharSequence.compare`.

## 10. Các lỗi hiểu sai thường gặp

1. **Cho rằng từ điển là thứ tự ngôn ngữ.** `compare("Z", "a") < 0` phản ánh mã UTF-16, không phải quy tắc xếp tên người. Dùng `Collator` cho văn bản theo locale.
2. **Giả định Unicode luôn là một `char` cho một ký tự.** Ký tự ngoài BMP dùng surrogate pair; chữ có dấu kết hợp cũng có thể gồm nhiều code point. `charAt` và `compare` hoạt động theo đơn vị UTF-16.
3. **Quên chuẩn hóa khi cần nhận dạng tương đương.** `"\u00E9"` và `"e\u0301"` không có cùng dãy `char`. Chuẩn hóa trước khi so sánh nếu yêu cầu nghiệp vụ coi chúng tương đương.
4. **Cho rằng `compare(...) == 0` tương đương `equals` cho mọi đối tượng.** `String` và `StringBuilder` có thể có nội dung như nhau nhưng `equals` khác nhau.
5. **Dựa vào giá trị `-1` hay `1` cụ thể.** Chỉ kiểm tra âm, bằng `0` hoặc dương; dùng `Integer.signum` nếu cần ba giá trị cố định.
6. **Sắp xếp các chuỗi có thể thay đổi mà không kiểm soát.** Đối tượng `StringBuilder` hoặc `StringBuffer` bị sửa sẽ làm thay đổi kết quả comparator; cân nhắc chuyển sang `String` bất biến.
7. **Mặc định so sánh được số tự nhiên.** `file10` và `file2` được so ký tự từ trái sang phải; cần comparator riêng nếu mục tiêu là `file2` đứng trước `file10`.

## 11. Tự kiểm tra

**Bài 1.** Dự đoán dấu của `CharSequence.compare("ab", "aba")`. Đáp án: **âm**, vì `"ab"` là tiền tố ngắn hơn.

**Bài 2.** Có nên viết `CharSequence.compare("An", new StringBuilder("An")) == 0` để kiểm tra trùng **nội dung**? **Có**, vì các đơn vị `char` bằng nhau. Có nên kết luận `"An".equals(new StringBuilder("An"))` là `true`? **Không**, vì `equals` không có hợp đồng chung cho mọi `CharSequence`.

**Bài 3.** Vì sao không dùng `CharSequence.compare` để sắp xếp danh sách tên tiếng Việt cho người dùng? Vì API không xét `Locale` hay quy tắc xếp từ của tiếng Việt; hãy dùng `Collator` và kiểm thử trên môi trường triển khai.

**Bài 4.** Một biểu tượng Unicode ngoài BMP đứng trước ký tự BMP khi so bằng `CharSequence.compare` nhưng có code point lớn hơn. Điều đó có thể xảy ra không? **Có**, do `compare` so các **đơn vị UTF-16 `char`**, không so toàn bộ code point.

## 12. Ghi nhớ

`CharSequence.compare` được bổ sung từ **Java 11** và hiện vẫn là cách trực tiếp để so sánh **thứ tự từ điển của các dãy `char`** thuộc nhiều kiểu `CharSequence`. Nó tìm vị trí `char` khác đầu tiên, so giá trị số rồi xét độ dài khi có cùng tiền tố; kết quả chỉ cần đọc theo **dấu âm, `0` hoặc dương**. Thứ tự này **không tự xử lý locale, Unicode normalization, code point hoặc số tự nhiên**. Khi cần sắp xếp văn bản tiếng Việt theo ngôn ngữ, dùng `Collator` với locale phù hợp; khi cần nhận dạng các dạng Unicode tương đương, chuẩn hóa `Normalizer` trước khi so sánh.

### Tài liệu chính thức

- [Java SE API — CharSequence, phương thức compare (Since: 11)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/CharSequence.html)
- [Java SE API — String, compareTo và contentEquals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [Java SE API — Collator, so sánh văn bản theo locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Collator.html)
- [Java SE API — Normalizer, chuẩn hóa Unicode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Consortium — Normalization FAQ](https://www.unicode.org/faq/normalization.html)
