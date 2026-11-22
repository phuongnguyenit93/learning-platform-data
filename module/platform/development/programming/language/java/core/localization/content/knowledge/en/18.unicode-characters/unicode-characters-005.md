# Dấu kết hợp, tiếng Việt và các cách biểu diễn Unicode tương đương trong Java

## Mục tiêu

Văn bản tiếng Việt có nhiều ký tự mang dấu: `á`, `à`, `ả`, `ã`, `ạ`, `ắ`, `ằ`, `ẫ`, `ậ`, `ế`, `ệ`, v.v. Người dùng nhìn thấy một chữ có dấu, nhưng Unicode có thể lưu chữ đó bằng **một code point đã được ghép sẵn (precomposed)** hoặc **một chữ cơ sở cộng các dấu kết hợp (combining marks)**.

Hai chuỗi nhìn giống nhau không nhất thiết có cùng dãy code point, cùng số phần tử trong `String`, hoặc bằng nhau theo `String.equals(...)`. Điều đó ảnh hưởng trực tiếp đến việc so sánh, tìm kiếm, lưu dữ liệu, xử lý tên file, xác thực đầu vào và bản địa hóa.

Sau bài học, bạn có thể:

- Phân biệt **code unit UTF-16**, **Unicode code point**, **combining mark** và **grapheme cluster** (cụm ký tự người dùng thường cảm nhận là một chữ).
- Mô tả vì sao `ắ` có thể là `U+1EAF` hoặc dãy `U+0061 U+0306 U+0301`, và vì sao hai cách này được coi là **tương đương chuẩn tắc (canonical equivalent)**.
- Sử dụng `java.text.Normalizer` với `NFC` và `NFD` để chuẩn hóa trước khi so sánh hoặc xử lý theo hợp đồng dữ liệu.
- Phân biệt `NFC/NFD` với `NFKC/NFKD` và hiểu tại sao chuẩn hóa tương thích có thể làm thay đổi những khác biệt mang ý nghĩa.
- Nhận diện những lỗi đặc thù tiếng Việt: đảo thứ tự dấu, xóa dấu để so sánh, coi `đ` và `d` là tương đương Unicode, cắt chuỗi theo `char`, hoặc dùng cách chuẩn hóa không nhất quán giữa các hệ thống.
- Viết ví dụ Java 17+ có thể chạy và lập bộ kiểm thử nhằm giữ đúng ý nghĩa chữ tiếng Việt.

**Trọng tâm:** biểu diễn Unicode và dấu kết hợp. Bài không nhằm dạy tất cả quy tắc chính tả tiếng Việt hay toàn bộ thuật toán xử lý ngôn ngữ tự nhiên.

## 1. Một chữ nhìn thấy không phải lúc nào cũng là một code point

Unicode gán số định danh gọi là **code point** cho nhiều ký tự và dấu. Mã được viết dưới dạng `U+XXXX`; ví dụ:

- `a`: `U+0061` (LATIN SMALL LETTER A).
- `á`: `U+00E1` (LATIN SMALL LETTER A WITH ACUTE).
- `ắ`: `U+1EAF` (LATIN SMALL LETTER A WITH BREVE AND ACUTE).
- `◌̆`: `U+0306` (COMBINING BREVE).
- `◌́`: `U+0301` (COMBINING ACUTE ACCENT).

Dấu tròn chấm `◌` trong cách minh họa dấu kết hợp chỉ giúp nhìn thấy vị trí đặt dấu; nó **không phải** một thành phần bắt buộc của chuỗi văn bản đã lưu.

Chữ `ắ` có ít nhất hai cách biểu diễn quan trọng:

```text
Cách A — dạng ghép sẵn:
U+1EAF
  ắ

Cách B — dạng phân rã:
U+0061 U+0306 U+0301
  a       ◌̆       ◌́
       (khi render cùng nhau: ắ)
```

Cách A có **một code point**; cách B có **ba code point**, nhưng hai chuỗi có thể render thành hình ảnh chữ giống nhau. Theo quy tắc Unicode, dạng ghép sẵn trên và dạng phân rã đúng thứ tự là **canonically equivalent**: chúng biểu diễn cùng một chuỗi ký tự theo quan hệ tương đương chuẩn tắc.

Điểm cần nắm:

> **Nhìn giống nhau không đủ để suy ra byte giống nhau, code point giống nhau hoặc `String.equals(...)` trả `true`.**

Đây không phải lỗi font hay lỗi riêng tiếng Việt; là đặc tính có chủ đích của Unicode để hỗ trợ nhiều cách biểu diễn văn bản, tương thích với dữ liệu được tạo từ các hệ thống và quy trình nhập liệu khác nhau.

## 2. Thuật ngữ: code unit, code point, combining mark, grapheme cluster

Trong Java, `String` lưu văn bản bằng các **UTF-16 code unit**. Nhiều code point trong vùng BMP, trong đó có các chữ tiếng Việt nêu trên và dấu kết hợp `U+0301`, được biểu diễn bằng một code unit. Các code point ngoài BMP thường cần **hai code unit (surrogate pair)**.

| Khái niệm | Đơn vị được đếm | API Java minh họa |
| --- | --- | --- |
| **UTF-16 code unit** | Đơn vị `char` 16-bit | `String.length()`, `charAt(i)` |
| **Unicode code point** | Giá trị vô hướng Unicode (trừ surrogate riêng lẻ) | `codePointCount(...)`, `codePoints()` |
| **Combining mark** | Code point có vai trò dấu/ký hiệu kết hợp | Có thể xem phân loại Unicode bằng `Character.getType(cp)` |
| **Grapheme cluster** | Nhóm code point thường được người dùng cảm nhận như một ký tự | Regex `\X` trong Java 17+ có hỗ trợ extended grapheme cluster |

Chẳng hạn dạng phân rã `a + ◌̆ + ◌́` có:

- `String.length() == 3` (ba UTF-16 code unit).
- `codePointCount(...) == 3` (ba code point).
- Một grapheme cluster trong cách phân đoạn Unicode tương ứng.

Còn dạng ghép sẵn `ắ` có `length() == 1` và một code point, vẫn thường là **một grapheme cluster**.

Không nên diễn đạt `String.length()` là “số chữ người dùng nhìn thấy”. Với một số ngôn ngữ hoặc emoji, sự khác biệt còn rõ hơn vì một cụm có thể chứa nhiều code point, đôi khi cả surrogate pair.

### Vì sao vấn đề này quan trọng khi cắt và giới hạn đầu vào?

Một biểu mẫu giới hạn 20 “ký tự hiển thị” khác với việc giới hạn 20 UTF-16 code unit. Nếu người dùng nhập tiếng Việt dạng NFD, cách đếm theo `length()` có thể ghi nhận nhiều đơn vị hơn dù số chữ họ nhìn thấy không thay đổi.

Ngược lại, nếu hệ thống có giới hạn **byte** khi ghi vào giao thức hoặc database, số byte UTF-8 lại là một phép đếm khác. Nên tách rõ ba nhu cầu:

1. **Giới hạn bộ nhớ/giao thức:** có thể dựa vào số byte hoặc UTF-16 code unit theo schema.
2. **Giới hạn code point:** có thể dựa vào `String.codePointCount(...)`.
3. **Giới hạn chữ người dùng nhìn thấy:** có thể dựa vào grapheme cluster với công cụ phân đoạn phù hợp.

Không thể dùng một con số `length()` rồi tuyên bố nó đồng thời đáp ứng cả ba yêu cầu.

## 3. Ký tự ghép sẵn và chuỗi dấu kết hợp trong tiếng Việt

Nhiều chữ tiếng Việt đã có code point ghép sẵn:

| Chữ hiển thị | Dạng ghép sẵn | Một dạng phân rã chuẩn tắc |
| --- | --- | --- |
| `á` | `U+00E1` | `U+0061 U+0301` |
| `ắ` | `U+1EAF` | `U+0061 U+0306 U+0301` |
| `ế` | `U+1EBF` | `U+0065 U+0302 U+0301` |
| `Á` | `U+00C1` | `U+0041 U+0301` |

Các thành phần của chữ `ắ`:

- `U+0061`: chữ cơ sở `a`.
- `U+0306`: dấu mũ ngắn/breve, góp phần tạo chữ `ă`.
- `U+0301`: dấu sắc/acute, biểu diễn thanh sắc.

Với `ế`, chữ cơ sở `e` được kết hợp với dấu mũ (`U+0302`) và dấu sắc (`U+0301`).

Một số hệ thống lưu chuỗi đã ghép sẵn; một số luồng xử lý có thể tạo chuỗi gồm các dấu kết hợp. Dù người dùng nhập cùng từ, dữ liệu đến từ bàn phím, trình chỉnh sửa, tệp, trình duyệt hay dịch vụ bên ngoài có thể mang dãy code point khác nhau.

**Không nên dự đoán dạng chuẩn hóa chỉ từ hệ điều hành hay bộ gõ.** Hãy kiểm tra và chuẩn hóa một cách có chủ đích khi nghiệp vụ yêu cầu.

### Tiếng Việt không chỉ có “dấu thanh”

Tiếng Việt kết hợp các đặc điểm khác nhau:

- **Dấu thanh:** sắc, huyền, hỏi, ngã, nặng.
- **Dấu tạo chữ cái:** mũ trong `â`/`ê`/`ô`; breve trong `ă`; horn trong `ơ`/`ư`.
- **Chữ cái riêng:** `đ`/`Đ`.

Nếu xử lý tất cả những dấu này đơn giản bằng cách “xóa mọi code point thuộc nhóm mark” thì hệ thống có thể làm mất cả khác biệt về chữ cái lẫn dấu thanh, ảnh hưởng trực tiếp đến ý nghĩa tiếng Việt.

## 4. Tương đương chuẩn tắc không đồng nghĩa chuỗi Java bằng nhau

`String.equals` so sánh nội dung theo các code unit. Nó không tự chuẩn hóa Unicode trước khi so sánh:

```java
String precomposed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(precomposed.equals(decomposed));
```

Đây là đoạn mã minh họa trong một phương thức. Stdout:

```text
false
```

Hai literal trên khi chạy biểu diễn cùng chữ `ắ` về mặt chuẩn tắc nhưng có dãy mã khác:

```text
precomposed: U+1EAF
decomposed:  U+0061 U+0306 U+0301
```

Nếu dùng trực tiếp làm key:

```java
Map<String, Integer> counts = new HashMap<>();
counts.put(precomposed, 1);
System.out.println(counts.containsKey(decomposed));
```

Trong phương thức có `import java.util.Map;` và `import java.util.HashMap;`, kết quả là `false`. Lý do: `HashMap` dùng `String.equals/hashCode` theo dãy code unit; không tự coi hai biểu diễn Unicode chuẩn tắc là cùng khóa.

Điều này có thể gây:

- Hai tài khoản/nhãn/định danh “nhìn giống nhau” nhưng tạo hai key khác nhau.
- Tra cứu theo tên thất bại dù chữ hiển thị trùng.
- Tập kết quả có bản ghi trùng về mặt hiển thị.
- So sánh nội dung giữa hệ thống trả khác nhau khi một phía chuẩn hóa, phía còn lại giữ nguyên chuỗi.

Giải pháp không phải mặc định dùng `equalsIgnoreCase`: đổi hoa/thường là một vấn đề khác với chuẩn hóa dấu kết hợp.

## 5. NFC và NFD: hai dạng chuẩn hóa chuẩn tắc

`java.text.Normalizer` cung cấp các dạng chuẩn hóa Unicode:

| Dạng | Ý nghĩa tổng quát | Hệ quả chính |
| --- | --- | --- |
| `Normalizer.Form.NFD` | Canonical Decomposition | Tách những tổ hợp ghép sẵn thành dãy code point phân rã chuẩn tắc, đồng thời sắp dấu theo quy tắc chuẩn tắc khi áp dụng |
| `Normalizer.Form.NFC` | Canonical Decomposition + Composition | Phân rã chuẩn tắc rồi kết hợp lại nơi được Unicode cho phép, tạo biểu diễn ghép sẵn phù hợp |
| `Normalizer.Form.NFKD` | Compatibility Decomposition | Phân rã cả các dạng tương thích, có thể làm mất khác biệt về kiểu trình bày/ký hiệu |
| `Normalizer.Form.NFKC` | Compatibility Decomposition + Composition | Chuẩn hóa tương thích rồi ghép, mạnh hơn NFC và không giữ mọi phân biệt ban đầu |

Với bài toán **coi các biểu diễn Unicode tương đương chuẩn tắc là cùng chuỗi**, `NFC` hoặc `NFD` là hai lựa chọn nền tảng. Trong nhiều trường hợp lưu trữ và trao đổi văn bản thông thường, `NFC` được chọn vì có thể sử dụng code point ghép sẵn khi thích hợp. Nhưng hợp đồng của hệ thống phải thống nhất lựa chọn này.

Ví dụ:

```java
import java.text.Normalizer;

String precomposed = "\u1EAF";
String decomposed = "a\u0306\u0301";

String left = Normalizer.normalize(
        precomposed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(left.equals(right));
```

Stdout:

```text
true
```

Một hệ thống có thể chọn NFD thay vì NFC nếu pipeline xử lý ký tự yêu cầu phân tách dấu, nhưng phải nhất quán ở mọi điểm tạo và so sánh dữ liệu. **Đừng chỉ chuẩn hóa một phía** rồi so với phía còn nguyên, cũng đừng trộn NFC và NFD tùy từng module.

### Normalizer.isNormalized

`Normalizer.isNormalized(text, Normalizer.Form.NFC)` giúp kiểm tra một chuỗi **đã ở NFC** hay chưa mà không phải tự diễn giải các mã Unicode. Nhưng kết quả “đã NFC” chỉ cho biết dạng biểu diễn phù hợp, **không chứng minh văn bản đúng chính tả, an toàn, hoặc đáp ứng quy tắc nghiệp vụ**.

Ví dụ, `"ma"` và `"má"` đều có thể ở NFC nhưng vẫn là hai chuỗi khác nghĩa.

## 6. Ví dụ Java 17+ hoàn chỉnh: so sánh, mã Unicode và grapheme cluster

Ví dụ sau tạo các chuỗi bằng Unicode escape trong Java source. Điều này giúp việc biên dịch không phụ thuộc terminal có hiển thị dấu tiếng Việt đúng hay không.

Tạo tệp `VietnameseNormalizationDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class VietnameseNormalizationDemo {
    private static String points(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u1EAF";           // ắ
        String decomposed = "a\u0306\u0301";   // a + breve + acute

        System.out.println("raw equals: "
                + composed.equals(decomposed));

        System.out.println("length: "
                + composed.length() + "/" + decomposed.length());

        System.out.println("code points: "
                + composed.codePointCount(0, composed.length())
                + "/" + decomposed.codePointCount(0, decomposed.length()));

        System.out.println("composed: " + points(composed));
        System.out.println("decomposed: " + points(decomposed));

        String nfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        String nfd = Normalizer.normalize(
                composed, Normalizer.Form.NFD);

        System.out.println("NFC equal: " + nfc.equals(composed));
        System.out.println("NFD equal: " + nfd.equals(decomposed));

        long clusters = Pattern.compile("\\X")
                .matcher(decomposed)
                .results()
                .count();

        System.out.println("grapheme clusters: " + clusters);

        String reversedMarks = "a\u0301\u0306";
        System.out.println("reversed equal: "
                + Normalizer.normalize(
                    reversedMarks, Normalizer.Form.NFC)
                  .equals(composed));

        String dStroke = "\u0111"; // đ
        System.out.println("d-stroke equals d after NFD: "
                + Normalizer.normalize(
                    dStroke, Normalizer.Form.NFD)
                  .equals("d"));

        String circledOne = "\u2460"; // ①
        System.out.println("NFKC circled one: "
                + Normalizer.normalize(
                    circledOne, Normalizer.Form.NFKC));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 VietnameseNormalizationDemo.java
java VietnameseNormalizationDemo
```

Stdout xác định với chương trình:

```text
raw equals: false
length: 1/3
code points: 1/3
composed: U+1EAF
decomposed: U+0061 U+0306 U+0301
NFC equal: true
NFD equal: true
grapheme clusters: 1
reversed equal: false
d-stroke equals d after NFD: false
NFKC circled one: 1
```

**Giải thích các dòng quan trọng:**

1. `equals` trực tiếp trả `false` vì dãy UTF-16 code unit khác nhau.
2. `length` và `codePointCount` trả 1/3 trong ví dụ này: tất cả code point liên quan đều nằm trong BMP nên mỗi code point dùng một UTF-16 code unit.
3. Hai dòng `points` cho thấy rõ `U+1EAF` so với `U+0061 U+0306 U+0301`.
4. Sau NFC hoặc NFD đúng chuẩn, các chuỗi tương đương chuẩn tắc được đưa về cùng biểu diễn, nên kết quả `true`.
5. Regex `\X` nhận chuỗi phân rã trên như **một extended grapheme cluster**, dù nó chứa ba code point.
6. Đảo dấu thành `a + acute + breve` **không** được Unicode tự đồng nhất với chuỗi chuẩn tắc `a + breve + acute` trong phép thử này.
7. `đ` không tự biến thành `d` qua NFD: hai chữ có khác biệt thực và không thuộc cặp tương đương chuẩn tắc đó.
8. `NFKC` biến ký tự `①` thành chữ số `1` vì chúng có quan hệ tương thích, cho thấy NFKC có thể gộp một số biểu diễn vốn không tương đương chuẩn tắc.

Khi áp dụng cho dữ liệu thật, đừng chỉ quan sát glyph đầu ra trên console; một số terminal hoặc font render dấu kết hợp khác nhau dù dãy code point là như nhau. Việc in code point giúp chẩn đoán một cách đáng tin hơn.

## 7. Thứ tự dấu kết hợp và canonical ordering

Unicode không xem **mọi hoán vị dấu kết hợp** là tương đương. Trong những trường hợp thích hợp, normalization có thể sắp lại các mark dựa trên *Canonical Combining Class* (CCC); nhưng thứ tự của các mark có cùng lớp kết hợp có thể vẫn mang ý nghĩa và không bị đảo tùy ý.

Với ví dụ đã kiểm thử:

```text
a + U+0306 + U+0301  -> NFC: U+1EAF (ắ)
a + U+0301 + U+0306  -> không có cùng NFC với U+1EAF
```

Không viết thuật toán “chuẩn hóa tiếng Việt” bằng cách tự ý sort tất cả dấu theo tên, theo code point hoặc theo nhóm “dấu thanh trước, dấu chữ sau”. Quy tắc canonical ordering của Unicode phức tạp hơn một phép sort bất kỳ, và thứ tự mark có thể ảnh hưởng việc ghép ký tự.

Cũng không nên xem một chuỗi sau NFC là **chính tả tiếng Việt hợp lệ**. Unicode normalization xử lý tính tương đương của biểu diễn; nó không kiểm tra đặt dấu thanh đúng âm tiết hoặc chữ có hợp lệ theo quy tắc ngôn ngữ hay không.

Nếu cần sửa lỗi bộ gõ hoặc sắp dấu theo chính tả tiếng Việt, đó là một tính năng ngôn ngữ riêng, phải có quy tắc và test chuyên biệt, không thể thay bằng mỗi `Normalizer.normalize(..., NFC)`.

## 8. Phân biệt chuẩn hóa Unicode với bỏ dấu tiếng Việt

Ví dụ:

```text
ma
má
mà
mả
mã
mạ
```

Các từ/cách viết trên **không phải chỉ là những biểu diễn Unicode khác nhau của cùng một chuỗi**. Dấu thanh tạo khác biệt ngôn ngữ. NFC không và không nên biến chúng thành cùng một giá trị.

Một cách “bỏ dấu” thường được thấy:

```java
String noMarks = Normalizer.normalize(
        text, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
```

Đây là đoạn mã minh họa trong một phương thức có biến `text`. `\p{M}` trong biểu thức chính quy Java đại diện nhóm ký tự Unicode loại Mark. Cách này **cố ý xóa thông tin**, không phải canonical normalization giữ nguyên ý nghĩa. Nó có thể gộp `"ma"`, `"má"`, `"mà"`, `"mã"`… thành cùng chuỗi `"ma"`.

Đặc biệt, `đ` không có phân rã chuẩn tắc thành `d` + dấu, nên phép xóa `\p{M}` sau NFD **không tự chuyển `đ` thành `d`**. Một số pipeline “bỏ dấu tiếng Việt” riêng còn tự map `đ → d`, nhưng đó là chính sách tìm kiếm/xử lý văn bản bổ sung, không phải Unicode normalization chuẩn tắc.

### Khi nào bỏ dấu là hợp lý?

Một chức năng gợi ý tìm kiếm có thể muốn người dùng nhập `"ca phe"` vẫn tìm được `"cà phê"`. Khi đó có thể tạo **search key phụ** mang tính xấp xỉ, sử dụng quy tắc bỏ dấu do sản phẩm xác định.

Tuy nhiên, không nên dùng search key đã bỏ dấu để:

- Ghi đè tên gốc của người dùng.
- Kiểm tra danh tính hay tính duy nhất tuyệt đối mà không có chính sách rõ.
- Thay thế giá trị pháp lý/cá nhân cần giữ chính xác.
- Quyết định hai chuỗi chắc chắn có cùng nghĩa.

Một kiến trúc phù hợp là **giữ văn bản gốc** và tạo thêm trường chuẩn hóa phục vụ tìm kiếm khi cần, kèm kiểm tra trùng/nhầm. Khi hiển thị cho người dùng, luôn sử dụng giá trị gốc hoặc giá trị Unicode đã được chuẩn hóa theo hợp đồng lưu trữ, không dùng văn bản đã bị xóa dấu.

## 9. NFC khác NFKC: không chuẩn hóa tương thích một cách vô thức

Hai chuỗi có thể *compatibility equivalent* mà không *canonically equivalent*. Ví dụ ký tự `①` (CIRCLED DIGIT ONE) và chữ số `1`:

```java
String circledOne = "\u2460";
String nfc = Normalizer.normalize(
        circledOne, Normalizer.Form.NFC);
String nfkc = Normalizer.normalize(
        circledOne, Normalizer.Form.NFKC);
```

Trong phương thức có import `Normalizer`:

- `nfc` vẫn biểu diễn ký hiệu số có vòng tròn `①`.
- `nfkc` trở thành ký tự chữ số `1`.

NFKC/NFKD có thể làm thay đổi những khác biệt trình bày hoặc cấu trúc vốn có ý nghĩa đối với một miền dữ liệu. Do đó:

- **Tên hiển thị và văn bản tiếng Việt nguyên bản:** thường cân nhắc NFC để thống nhất các biểu diễn chuẩn tắc, không tự động dùng NFKC.
- **Mã định danh có quy tắc chuẩn hóa riêng:** chỉ dùng compatibility normalization nếu schema, yêu cầu bảo mật và tính tương thích đã quy định.
- **Tìm kiếm có khả năng tương thích rộng:** có thể cần bước chuyển đổi riêng cho index tìm kiếm, nhưng phải chấp nhận nguy cơ gộp những chuỗi khác nhau.

NFKC không phải “phiên bản NFC tốt hơn”. Nó giải quyết bài toán khác; trong một số bối cảnh bảo mật, NFKC còn có vai trò trong những profile đặc biệt, nhưng không tự loại bỏ mọi ký tự gây nhầm hình dạng.

## 10. Dữ liệu đầu vào, lưu trữ và so sánh ở ranh giới hệ thống

Một lỗi thực tế dễ gặp:

```text
Service A lưu:  "ắ"                -> U+1EAF
Service B gửi: "a\u0306\u0301"      -> U+0061 U+0306 U+0301

Màn hình: trông giống nhau
String.equals: false
Lookup HashMap/cache: có thể không tìm thấy
```

Nếu nghiệp vụ xem hai cách biểu diễn chuẩn tắc là tương đương, cần một **chính sách normalization nhất quán**. Một cách đơn giản:

1. Nhận Unicode hợp lệ từ nguồn đầu vào (form, tệp, API).
2. Kiểm tra yêu cầu về độ dài/nhóm ký tự và các chính sách nghiệp vụ khác.
3. Chuẩn hóa `NFC` tại ranh giới được xác định, **trước khi lập key so sánh/lưu trữ nếu đó là hợp đồng đã chọn**.
4. Dùng cùng dạng chuẩn hóa để tạo query, cache key, index và unique constraint thuộc logic ứng dụng.
5. Giữ lại bản gốc riêng nếu cần kiểm toán hoặc tái tạo đúng văn bản người dùng đã nhập.
6. Khi thay đổi chính sách normalization cho hệ thống đang vận hành, lên kế hoạch migration, giải quyết các giá trị trùng sau chuẩn hóa và đồng bộ nhiều dịch vụ.

Hàm chuẩn hóa minh họa:

```java
import java.text.Normalizer;
import java.util.Objects;

public final class UnicodeKeys {
    private UnicodeKeys() {}

    public static String canonicalKey(String input) {
        Objects.requireNonNull(input, "input");
        return Normalizer.normalize(input, Normalizer.Form.NFC);
    }
}
```

Lớp này có thể biên dịch thành `UnicodeKeys.java`, nhưng không có `main` để chạy độc lập. Nó chỉ xử lý tương đương chuẩn tắc. Nếu yêu cầu còn so sánh không phân biệt hoa/thường, xử lý khoảng trắng, loại ký tự cấm hay unicode confusables thì phải xây dựng **chính sách riêng** thay vì lặng lẽ nhét vào normalization.

### Cơ sở dữ liệu và unique constraint

Một database có thể dùng collation khác nhau: có nơi coi các dạng tương đương là cùng chuỗi, nơi khác có thể phân biệt hoặc có quy tắc chuẩn hóa riêng. **Không giả định** database, Java `HashMap` và dịch vụ tìm kiếm dùng cùng so sánh văn bản.

Nếu hệ thống cần tính duy nhất theo “cùng chuỗi sau NFC”, nên xác định cách tạo khóa chuẩn hóa, thiết lập index/constraint thích hợp và kiểm tra sự nhất quán ở mọi đường ghi. Khi bổ sung normalization vào dữ liệu cũ, hai bản ghi đã tồn tại có thể cùng khóa sau khi chuẩn hóa; cần chính sách xử lý collision, không xóa dữ liệu tự động.

### API và byte serialization

JSON, UTF-8 và các giao thức Unicode có thể truyền được cả dạng NFC lẫn NFD. Việc hai chuỗi có cùng biểu hiện trực quan **không buộc byte UTF-8 của chúng giống nhau**. Nếu hệ thống tính chữ ký số, hash, ETag hoặc dùng chuỗi làm khóa cache, khác biệt byte có thể khiến kết quả khác.

Chỉ chuẩn hóa **trước khi ký/hash** nếu cả phía gửi và nhận có cùng hợp đồng chuẩn hóa; không tự sửa thông điệp đã ký hoặc JSON tùy ý rồi kỳ vọng chữ ký vẫn hợp lệ. Việc canonical hóa JSON để ký còn có quy tắc riêng (trật tự trường, escapes, kiểu số…) không được giải quyết chỉ bằng `Normalizer`.

## 11. So sánh theo ngôn ngữ với Collator là một vấn đề khác

`String.equals` dựa trên nội dung code unit; `Normalizer` giải quyết biểu diễn Unicode; `java.text.Collator` giải quyết việc **so sánh/sắp xếp theo quy ước ngôn ngữ**.

Ví dụ:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

Đây là đoạn minh họa bên trong phương thức. `Collator` có các mức strength giúp quyết định những khác biệt chữ và dấu có được xét đến khi so sánh/sắp xếp hay không. Tùy strength và dữ liệu collation, hai chuỗi **khác nhau về dấu thanh** có thể được so sánh là gần nhau hơn, hoặc có thứ tự riêng.

Cần phân biệt:

- **NFC/NFD:** cùng một chuỗi xét theo tương đương chuẩn tắc, không thay ý nghĩa dấu thanh.
- **Collation:** so sánh/định thứ tự theo ngôn ngữ với strength được chọn.
- **Accent-insensitive search:** một yêu cầu tìm kiếm xấp xỉ, có thể sử dụng collation/search key hoặc bộ tìm kiếm chuyên dụng.
- **Exact equality cho định danh:** cần hợp đồng rõ ràng; thường không dùng comparator bỏ qua dấu một cách vô thức.

Nếu chỉ muốn đảm bảo `"ắ"` và `"a\u0306\u0301"` được xem là cùng dữ liệu theo canonical equivalence, normalize NFC trước rồi dùng `equals` là cách minh bạch. Nếu muốn sắp xếp danh sách từ tiếng Việt theo đúng thứ tự từ vựng, sử dụng công cụ collation theo locale và kiểm thử với dữ liệu người dùng.

## 12. Kiểm tra ký tự người dùng nhìn thấy

Nhiều lỗi UI xuất hiện khi code duyệt từng `char`:

```java
for (int i = 0; i < text.length(); i++) {
    char part = text.charAt(i);
    // Không giả định part là một chữ hoàn chỉnh người dùng thấy.
}
```

Đây là đoạn minh họa trong một phương thức. Với `"a\u0306\u0301"`, vòng lặp nhận ba `char` riêng: chữ a và hai dấu kết hợp. Nếu dùng `substring(0, 1)`, bạn chỉ giữ `a` và làm mất dấu; nếu cắt giữa cụm, phần sau có thể bắt đầu bằng dấu kết hợp không có chữ cơ sở.

`String.codePoints()` giải quyết việc duyệt **code point** (tránh cắt đôi surrogate pair), nhưng vẫn **không** tự gom các dấu kết hợp với chữ cơ sở. Nếu yêu cầu cắt theo cụm chữ người dùng nhìn thấy, có thể dùng regex Java hỗ trợ extended grapheme cluster:

```java
import java.util.regex.Pattern;

String text = "a\u0306\u0301";
long clusterCount = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();
```

Đây là đoạn minh họa bên trong phương thức; `clusterCount` bằng 1 trong ví dụ. Với giao diện phức tạp (emoji, tổ hợp ký tự nhiều script), cần cân nhắc phiên bản Unicode/JDK và thư viện phân đoạn phù hợp; một grapheme cluster vẫn không luôn tương đương “một ký tự về ngữ nghĩa” trong mọi bối cảnh.

### Không nên giới hạn mọi field bằng regex ASCII

Kiểm tra như `^[A-Za-z]+$` sẽ loại tiếng Việt có dấu và chữ `đ`. Thậm chí regex chỉ chấp nhận một số khoảng chữ cái ghép sẵn có thể loại chuỗi NFD chứa combining mark. Nếu mục tiêu là “cho phép tên tiếng Việt”, hãy xây quy tắc hỗ trợ chữ và dấu kết hợp thích hợp, cân nhắc normalization và giải thích rõ chính sách ký tự được phép.

Không dùng `\\w` hoặc `Character.isLetter` một cách máy móc để tuyên bố mọi chuỗi tên đều hợp lệ: còn dấu kết hợp, khoảng trắng, dấu nối, dấu nháy, nhiều hệ chữ, tính bảo mật và ngữ cảnh nghiệp vụ.

## 13. Kiểm thử Unicode tiếng Việt đúng phạm vi

Một bộ test phù hợp nên gồm:

| Nhóm | Test minh họa | Kỳ vọng |
| --- | --- | --- |
| Tương đương chuẩn tắc | `"\u1EAF"` và `"a\u0306\u0301"` | `equals` raw khác; sau NFC bằng |
| Phân rã NFD | `"\u1EAF"` | Dãy `U+0061 U+0306 U+0301` |
| Thứ tự dấu | `"a\u0306\u0301"` so với `"a\u0301\u0306"` | Không tự coi mọi hoán vị là tương đương |
| Chữ cái riêng | `"đ"` và `"d"` | NFD không làm chúng bằng nhau |
| Dấu thanh khác nhau | `"ma"` và `"má"` | NFC không gộp chúng |
| Đếm ký tự | `"\u1EAF"` so với `"a\u0306\u0301"` | `length` khác; grapheme count vẫn là 1 trong ví dụ |
| Chữ tương thích | `"\u2460"` và `"1"` | NFKC có thể gộp, NFC không |
| Hash/map | Key từ NFC vs NFD | Lookup theo key chưa normalize có thể trượt |
| Tên file/DB | Tên hiển thị giống nhưng byte khác | Cần chính sách ranh giới rõ ràng |
| Tìm kiếm bỏ dấu | `ma/má/mà` | Có thể gộp theo search policy, không thay dữ liệu gốc |

Khi test, nên so sánh dãy code point hoặc bytes một cách có chủ đích; screenshot hoặc mắt người nhìn không đủ phát hiện các khác biệt normalization.

### Kiểm tra tính nhất quán qua nhiều lớp

Với API lưu tên người dùng, có thể tạo hai request cùng nội dung tiếng Việt nhưng một dùng NFC, một dùng NFD. Xác định rõ:

1. Hệ thống có chấp nhận cả hai không?
2. Có chuẩn hóa lúc ghi, lúc tra cứu hay cả hai không?
3. Có yêu cầu lưu đúng dãy code point gốc cho mục đích nào không?
4. Có sinh hai bản ghi hoặc hai khóa cache khác nhau không?
5. Unique constraint hoạt động theo canonical equivalence hay theo một collation khác?
6. Kết quả hiển thị có giữ đúng dấu tiếng Việt và thứ tự từ không?

Các câu hỏi này nên được giải quyết **trước khi** thêm normalization vào một hệ thống dữ liệu đang tồn tại, vì thay đổi khóa chuẩn hóa có thể tạo collision giữa những bản ghi vốn khác nhau.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Người dùng thấy một chữ thì `length()` phải bằng 1” | UTF-16 code unit không phải grapheme cluster | Phân biệt `length`, `codePointCount` và grapheme |
| “Hai chữ nhìn giống nhau thì `String.equals` bằng nhau” | Chuỗi có thể khác dạng NFC/NFD | Chuẩn hóa cùng dạng trước khi so sánh nếu hợp đồng yêu cầu |
| “Mọi dấu tiếng Việt đều là một code point ghép sẵn” | Unicode còn biểu diễn dấu bằng combining marks | Nhận diện các dãy dấu và normalization |
| “Đảo dấu kết hợp theo bất kỳ thứ tự nào cũng như nhau” | Canonical ordering không phải mọi hoán vị | Dùng `Normalizer`, không tự sort mark |
| “NFD sẽ biến `đ` thành `d`” | `đ` không có phân rã chuẩn tắc như vậy | Muốn map `đ/d` phải có chính sách riêng |
| “NFC xóa dấu tiếng Việt” | NFC giữ khác biệt chữ và dấu | Không lẫn normalization với accent stripping |
| “NFKC luôn là lựa chọn tốt hơn” | Có thể gộp ký tự tương thích vốn cần phân biệt | Chọn NFC/NFKC theo hợp đồng dữ liệu |
| “Chỉ cần dùng `equalsIgnoreCase`” | Case-insensitive không giải quyết canonical equivalence | Normalize độc lập với việc xử lý case |
| “`codePoints()` duyệt một chữ người dùng thấy mỗi lần” | Một grapheme có thể chứa nhiều code point | Dùng công cụ phân đoạn grapheme nếu cần |
| “Dùng dấu đã bỏ để làm tên chính” | Mất ý nghĩa và có thể tạo nhiều xung đột | Giữ tên gốc, tạo search key phụ nếu cần |
| “NFC là kiểm tra chính tả tiếng Việt” | Normalizer không biết ngữ pháp/chính tả | Validation ngôn ngữ là bước riêng |
| “UTF-8 luôn tự chuyển về NFC” | Encoding không đồng nghĩa Unicode normalization | Chuẩn hóa theo chính sách, sau đó encode |
| “Database và Java luôn so sánh chữ giống nhau” | Collation, normalization và so sánh byte khác nhau | Kiểm thử từ API tới DB/cache/index |

## 15. Bài tập thực hành

**Bài 1 — biểu diễn cùng một chữ.** Viết một chuỗi `"\u1EAF"` và một chuỗi `"a\u0306\u0301"`. So sánh bằng `equals`, in `length` và `codePointCount`. Giải thích vì sao những kết quả khác nhau dù cả hai hiển thị thành `ắ`.

**Bài 2 — chuẩn hóa NFC/NFD.** Dùng `Normalizer.normalize(..., NFC)` và `NFD` cho hai chuỗi trên. In mọi code point ở dạng `U+XXXX` và kiểm tra kết quả sau chuẩn hóa.

**Bài 3 — thứ tự dấu.** So sánh `a + U+0306 + U+0301` với `a + U+0301 + U+0306`. Sau NFC, chúng có bằng nhau không? Giải thích vì sao không nên tự sắp xếp các dấu theo ý muốn.

**Bài 4 — phân biệt chữ khác nhau.** Thử normalize `"đ"` và `"d"`, `"má"` và `"ma"`. Vì sao chuẩn hóa giữ nguyên những khác biệt này? Khi nào một chức năng tìm kiếm xấp xỉ có thể muốn gộp chúng?

**Bài 5 — giới hạn trường nhập.** Một form giới hạn 10 “ký tự nhìn thấy” nhưng code dùng `String.length() <= 10`. Hãy chỉ ra tình huống người dùng nhập tiếng Việt dạng phân rã có thể bị tính nhiều ký tự hơn. Thiết kế kiểm thử theo grapheme cluster.

**Bài 6 — định danh.** Hai request tạo tên hiển thị giống nhau nhưng một dạng NFC, một dạng NFD. Nếu dùng key `HashMap` và unique constraint database, kết quả có thể khác nhau thế nào? Hãy đề xuất chính sách chuẩn hóa ở ranh giới hệ thống, xử lý dữ liệu cũ và kiểm tra collision.

**Bài 7 — NFKC.** Chạy `Normalizer.normalize("\u2460", NFKC)`. Vì sao nhận `1` không đồng nghĩa đây là một trường hợp tương đương chuẩn tắc như `ắ` và chuỗi phân rã của nó?

**Bài 8 — tìm kiếm.** Thiết kế một chức năng tìm kiếm tên tiếng Việt không bắt buộc nhập dấu. Hãy nêu những gì phải lưu ở trường gốc, những gì có thể đưa vào chỉ mục tìm kiếm phụ và cách tránh dùng kết quả đã bỏ dấu làm định danh tuyệt đối.

## 16. Ghi nhớ

**Dấu kết hợp là code point Unicode thực sự.** Một chữ tiếng Việt như `ắ` có thể được lưu bằng một code point ghép sẵn hoặc bằng dãy chữ cơ sở + các dấu kết hợp. Hai chuỗi có thể trông giống nhau nhưng khác số code unit, code point và byte, khiến `String.equals`, `HashMap` hoặc hệ thống lưu trữ không tự coi là trùng.

**`Normalizer.Form.NFC` và `NFD` giải quyết tương đương chuẩn tắc, không xóa dấu và không sửa chính tả.** Cần phân biệt với `NFKC`/`NFKD` (tương đương tương thích), collation theo ngôn ngữ và quy tắc tìm kiếm bỏ dấu. `đ` không biến thành `d` qua NFD, và đổi thứ tự dấu kết hợp không luôn giữ nguyên chuỗi theo Unicode.

Trong Java, hãy sử dụng `Normalizer` để chuẩn hóa theo chính sách đã công bố, dùng `codePoints()` khi cần duyệt code point, và dùng công cụ phân đoạn grapheme khi cần tính/cắt số chữ người dùng nhìn thấy. Lưu văn bản gốc khi nghiệp vụ cần bảo toàn, kiểm soát dữ liệu chuẩn hóa xuyên suốt API/database/cache, và kiểm thử kỹ Unicode tiếng Việt ở cả dạng NFC lẫn NFD.

**Nguyên tắc cốt lõi:** *Chuẩn hóa biểu diễn để so sánh nhất quán — không đánh đồng chuẩn hóa Unicode với loại bỏ khác biệt ngôn ngữ.*

### Tài liệu tham khảo

- [`java.text.Normalizer` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [`java.lang.String` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`java.util.regex.Pattern` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Normalization Forms (UAX #15)](https://unicode.org/reports/tr15/)
- [Unicode Text Segmentation (UAX #29)](https://unicode.org/reports/tr29/)
