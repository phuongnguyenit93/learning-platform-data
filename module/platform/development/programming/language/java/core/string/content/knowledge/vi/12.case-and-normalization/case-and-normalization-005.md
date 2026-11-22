# Normalizer và các dạng NFC, NFD, NFKC, NFKD trong Java

Hai chuỗi trông giống nhau trên màn hình chưa chắc chứa cùng dãy ký tự Unicode. Chẳng hạn, chữ **é** có thể được biểu diễn bằng một code point `U+00E9` hoặc bằng chữ **e** `U+0065` theo sau dấu sắc kết hợp `U+0301`. Với Java, `String.equals()` so sánh dãy code unit UTF-16, nên hai chuỗi ấy **không bằng nhau theo `equals()`** dù có thể hiển thị giống hệt.

Unicode định nghĩa các **dạng chuẩn hóa** (*normalization forms*) để đưa văn bản về cách biểu diễn nhất quán theo các quy tắc tương đương. Java cung cấp `java.text.Normalizer` với bốn dạng **NFC, NFD, NFKC, NFKD**. Hiểu đúng bốn dạng giúp so sánh, tìm kiếm, lưu khóa và trao đổi dữ liệu đa ngôn ngữ một cách có chủ đích, đồng thời tránh làm thay đổi ý nghĩa văn bản ngoài mong muốn.

## 1. Normalization là gì và không phải là gì?

*Unicode normalization* biến đổi **dãy code point** theo quy tắc Unicode: phân rã một số ký tự, sắp xếp lại dấu kết hợp theo thứ tự chuẩn tắc, và có thể ghép một số dãy đã phân rã thành ký tự dựng sẵn. Hai dạng dữ liệu khác nhau nhưng được Unicode coi là tương đương theo loại tương đương đã chọn sẽ có cùng biểu diễn chuẩn hóa trong phạm vi quy tắc ấy.

Ví dụ cùng biểu diễn chữ é:

```text
Dạng dựng sẵn:   U+00E9               é
Dạng tổ hợp:     U+0065 U+0301         e + ◌́

Trước khi chuẩn hóa:  hai dãy code point khác nhau
Sau khi về NFC:       cả hai thành U+00E9
Sau khi về NFD:       cả hai thành U+0065 U+0301
```

Trong bảng trên, ký hiệu `◌́` chỉ giúp nhìn thấy dấu sắc kết hợp, không phải code point bổ sung cần nhập vào dữ liệu thật.

**Normalization không đồng nghĩa với:**

- Chuyển chữ hoa thành chữ thường; `"Java"` và `"java"` vẫn là hai chuỗi khác nhau sau NFC/NFD/NFKC/NFKD.
- Bỏ dấu tiếng Việt hoặc phiên âm. `"á"` không biến thành `"a"` chỉ vì gọi `Normalizer.normalize(...)`.
- Dịch, sửa chính tả, thay dấu cách tùy ý hoặc xóa ký tự vô hình.
- So sánh theo quy tắc của một ngôn ngữ (*collation*); ví dụ cách sắp xếp từ điển là vấn đề khác.
- Bảo đảm hai chuỗi trông giống nhau sẽ bằng nhau. Các ký tự khác bảng chữ viết có thể trông giống nhau mà vẫn không tương đương Unicode; chuẩn hóa không giải quyết mọi ký tự dễ nhầm (*confusables*).

Quan trọng: chuẩn hóa làm thay đổi **chuỗi biểu diễn**, không thay thế việc chọn chính sách so sánh phù hợp cho từng bài toán.

## 2. Hai kiểu tương đương của Unicode

### 2.1. Tương đương chuẩn tắc — canonical equivalence

Hai dãy code point *canonically equivalent* nếu Unicode coi chúng là những biểu diễn chuẩn tắc khác nhau của cùng văn bản trừu tượng. Một ví dụ phổ biến là:

- `U+00E9`: chữ é dựng sẵn.
- `U+0065 U+0301`: chữ e kết hợp dấu sắc.

Hai dãy trên khác nhau về độ dài và mã, nhưng được coi là tương đương chuẩn tắc. Các dạng **NFC** và **NFD** bảo toàn loại tương đương này. Đổi giữa chúng có thể thay đổi số code point, số code unit, byte khi mã hóa, hoặc chỉ số trong chuỗi.

### 2.2. Tương đương tương thích — compatibility equivalence

Một số ký tự Unicode biểu diễn hình thức trình bày hoặc ký hiệu có ý nghĩa lịch sử/chức năng riêng nhưng có **compatibility decomposition** sang dãy ký tự thông thường. Ví dụ:

- `①` (`U+2460`, chữ số 1 trong vòng tròn) có dạng tương thích là `1` (`U+0031`).
- `ﬃ` (`U+FB03`, ligature) có dạng tương thích là ba chữ `f`, `f`, `i`.
- `Ａ` (`U+FF21`, chữ A fullwidth) có dạng tương thích là `A` (`U+0041`).

Các cặp này **không nhất thiết tương đương chuẩn tắc**. Chuyển bằng **NFKC/NFKD** có thể xóa đi sự khác biệt về kiểu trình bày hoặc tính năng của ký hiệu. Điều đó có ích khi dữ liệu cần so sánh theo dạng ký tự thông thường, nhưng cũng có thể **mất thông tin phân biệt** mà bài toán thật sự cần giữ.

Không suy diễn rằng hai ký hiệu có hình dáng gần nhau đều tương đương tương thích. Chỉ những ánh xạ theo dữ liệu và quy tắc Unicode tương ứng mới được áp dụng.

## 3. Bốn dạng NFC, NFD, NFKC, NFKD

Tên dạng có thể nhớ theo hai trục:

- **C** = *Composition*: thực hiện phân rã phù hợp, sắp xếp dấu kết hợp theo chuẩn, rồi **ghép lại** những dãy được phép.
- **D** = *Decomposition*: **phân rã** theo quy tắc, không ghép lại sau cùng.
- **K** = *Compatibility*: ngoài phân rã chuẩn tắc, còn áp dụng **phân rã tương thích**. Chữ K là một phần của tên Unicode chính thức.

| Dạng | Tên đầy đủ | Cách thực hiện ở mức khái niệm | Đặc điểm cần nhớ |
|---|---|---|---|
| **NFD** | Normalization Form D | Phân rã chuẩn tắc + sắp xếp chuẩn tắc | Giữ các khác biệt không tương đương chuẩn tắc |
| **NFC** | Normalization Form C | Phân rã chuẩn tắc + sắp xếp + ghép chuẩn tắc | Thường thuận tiện làm dạng nhất quán cho văn bản thông thường |
| **NFKD** | Normalization Form KD | Phân rã chuẩn tắc **và tương thích** + sắp xếp | Có thể đưa ký hiệu trình bày về ký tự cơ sở |
| **NFKC** | Normalization Form KC | Phân rã chuẩn tắc **và tương thích** + sắp xếp + ghép chuẩn tắc | Kết hợp dạng ghép và các phép gộp tương thích |

Ví dụ diễn giải:

| Đầu vào | NFC | NFD | NFKC | NFKD |
|---|---|---|---|---|
| `é` (U+00E9) | `é` | `e` + dấu sắc | `é` | `e` + dấu sắc |
| `e` + dấu sắc (U+0065 U+0301) | `é` | `e` + dấu sắc | `é` | `e` + dấu sắc |
| `①` (U+2460) | `①` | `①` | `1` | `1` |
| `ﬃ` (U+FB03) | `ﬃ` | `ﬃ` | `ffi` | `ffi` |
| `Ａ` (U+FF21) | `Ａ` | `Ａ` | `A` | `A` |

**Không có quy luật “NFC luôn có ít ký tự hơn NFD”.** Có những dãy phân rã mà Unicode không cho phép ghép thành một ký tự dựng sẵn. Thứ tự và quy tắc ghép còn chịu các giới hạn như *composition exclusions*. Bởi vậy chữ C là “cố gắng ghép theo quy tắc”, không phải “bảo đảm một code point cho mỗi chữ mà người dùng nhìn thấy”.

Các dạng chuẩn hóa đều có tính **idempotent**: áp dụng **cùng một dạng** lần nữa sẽ cho cùng nội dung:

```text
normalize(normalize(s, NFC), NFC) == normalize(s, NFC)
```

Dòng trên biểu thị **đẳng thức về nội dung**, không phải bảo đảm hai tham chiếu Java bằng nhau bằng `==`.

## 4. API `java.text.Normalizer` trong Java 17+

Lớp `java.text.Normalizer` nằm trong thư viện chuẩn Java; không cần dependency ngoài. Hai phương thức tĩnh cần biết:

```java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
boolean alreadyNormalized =
        Normalizer.isNormalized(input, Normalizer.Form.NFC);
```

Đây là **đoạn minh họa**, giả sử `input` đã được khai báo là một `String` không null. Bốn hằng enum tương ứng là:

```java
Normalizer.Form.NFC
Normalizer.Form.NFD
Normalizer.Form.NFKC
Normalizer.Form.NFKD
```

- `normalize(String source, Normalizer.Form form)` trả một `String` có nội dung ở dạng yêu cầu.
- `isNormalized(String source, Normalizer.Form form)` cho biết nội dung **đã** thỏa dạng đó chưa. Phương thức này đặc biệt hữu ích khi muốn kiểm tra dữ liệu hoặc tránh thực hiện bước chuẩn hóa không cần thiết theo luồng ứng dụng.
- `String` là immutable: không có thao tác nào ở đây sửa nội dung chuỗi nguồn. Muốn giữ kết quả, dùng biến mới hoặc gán `input = Normalizer.normalize(input, form);`.
- Một chuỗi có thể đồng thời thỏa **nhiều dạng**. Ví dụ `"abc"` đã ở cả NFC, NFD, NFKC và NFKD.
- `Normalizer` xử lý dữ liệu Unicode theo phiên bản được hỗ trợ bởi bản triển khai JDK; với các ký tự Unicode mới hơn, cần xem khả năng hỗ trợ của môi trường Java mục tiêu.

### Ví dụ 1: chữ é theo NFC và NFD

Lưu thành **`CanonicalNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CanonicalNormalizationDemo {
    private static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw equals: " + composed.equals(decomposed));

        String nfcA = Normalizer.normalize(composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals: " + nfcA.equals(nfcB));
        System.out.println("NFC points: " + codePoints(nfcB));

        String nfdA = Normalizer.normalize(composed, Normalizer.Form.NFD);
        String nfdB = Normalizer.normalize(decomposed, Normalizer.Form.NFD);
        System.out.println("NFD equals: " + nfdA.equals(nfdB));
        System.out.println("NFD points: " + codePoints(nfdA));

        System.out.println("decomposed already NFC: "
                + Normalizer.isNormalized(decomposed, Normalizer.Form.NFC));
        System.out.println("decomposed already NFD: "
                + Normalizer.isNormalized(decomposed, Normalizer.Form.NFD));

        String nfcTwice = Normalizer.normalize(nfcB, Normalizer.Form.NFC);
        System.out.println("NFC idempotent: " + nfcB.equals(nfcTwice));
    }
}
```

Chạy tại thư mục chứa tệp, dùng JDK 17+:

```bash
javac CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
```

**Stdout:**

```text
raw equals: false
NFC equals: true
NFC points: U+00E9
NFD equals: true
NFD points: U+0065 U+0301
decomposed already NFC: false
decomposed already NFD: true
NFC idempotent: true
```

`composed.equals(decomposed)` ban đầu là `false` vì khác chuỗi code unit UTF-16. Sau NFC, cả hai cùng có `U+00E9`; sau NFD, cả hai cùng có `U+0065 U+0301`. `isNormalized` kiểm tra **dạng chuẩn hóa hiện có**, không kiểm tra chuỗi có phải tiếng Việt/tiếng Anh hợp lệ, và cũng không loại bỏ dấu. `NFC idempotent` minh họa áp dụng lại một dạng đã đạt chuẩn không làm thay đổi nội dung.

## 5. Ví dụ 2: NFKC/NFKD khác NFC/NFD ở đâu?

Điểm đặc trưng của hai dạng có **K** là chúng xử lý cả ánh xạ tương thích. Để tránh sự phụ thuộc vào font hiển thị ký tự đặc biệt, ví dụ dưới đây in **mã code point Unicode** thay vì in trực tiếp glyph kết quả.

Lưu thành **`CompatibilityNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CompatibilityNormalizationDemo {
    private static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String name, String input) {
        System.out.println(name + " NFC: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFC)));
        System.out.println(name + " NFD: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFD)));
        System.out.println(name + " NFKC: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFKC)));
        System.out.println(name + " NFKD: " + points(
                Normalizer.normalize(input, Normalizer.Form.NFKD)));
    }

    public static void main(String[] args) {
        show("circled-one", "\u2460");
        show("ligature-ffi", "\uFB03");
        show("fullwidth-A", "\uFF21");
    }
}
```

```bash
javac CompatibilityNormalizationDemo.java
java CompatibilityNormalizationDemo
```

**Stdout:**

```text
circled-one NFC: U+2460
circled-one NFD: U+2460
circled-one NFKC: U+0031
circled-one NFKD: U+0031
ligature-ffi NFC: U+FB03
ligature-ffi NFD: U+FB03
ligature-ffi NFKC: U+0066 U+0066 U+0069
ligature-ffi NFKD: U+0066 U+0066 U+0069
fullwidth-A NFC: U+FF21
fullwidth-A NFD: U+FF21
fullwidth-A NFKC: U+0041
fullwidth-A NFKD: U+0041
```

Các kết quả cho thấy:

1. NFC/NFD không tự biến `①` thành `1`, `ﬃ` thành `ffi` hoặc `Ａ` thành `A` vì các cặp này chỉ liên hệ qua **tương đương tương thích**.
2. NFKC/NFKD có thể làm mất thông tin về kiểu ký hiệu, hình thức trình bày hoặc chiều rộng ký tự. Nếu phân biệt `①` và `1` là quan trọng trong dữ liệu, **không được mặc định chọn NFKC**.
3. Với các chuỗi ví dụ không có dãy cần ghép sau phân rã tương thích, đầu ra NFKC và NFKD trùng nhau. Điều đó **không** có nghĩa hai dạng luôn như nhau: chúng khác biệt khi có thành phần cần ghép chuẩn tắc sau bước phân rã.

## 6. Ký tự tổ hợp, thứ tự dấu và những điều dễ hiểu sai

Một dãy Unicode có thể gồm ký tự cơ sở và nhiều dấu kết hợp. Chuẩn hóa không chỉ thay một ký tự dựng sẵn bằng hai ký tự hoặc ngược lại; nó còn áp dụng **thứ tự chuẩn tắc** dựa trên *Canonical Combining Class* khi quy tắc cho phép.

Vì vậy:

- Những dãy cùng nghĩa chuẩn tắc nhưng có thứ tự dấu khác nhau đôi khi được đưa về cùng thứ tự chuẩn. Không nên tùy ý hoán đổi mọi dấu; Unicode có các quy tắc và ngoại lệ cụ thể.
- Một dấu kết hợp không nhất thiết có ký tự dựng sẵn tương ứng với mọi chữ cơ sở. Sau NFC vẫn có thể còn nhiều code point.
- “Một code point” không đồng nghĩa “một ký tự người dùng thấy”. Một **grapheme cluster** có thể có nhiều code point, ngay cả sau khi đã chuẩn hóa.
- `String.length()` đếm code unit UTF-16, `codePointCount(0, length())` đếm code point, còn số cụm ký tự hiển thị là phép đo khác. Chuẩn hóa có thể thay đổi hai phép đếm đầu mà vẫn cho biểu diễn nhìn tương tự.

Ví dụ:

```text
Trước: "e" + U+0301
  UTF-16 code units = 2
  Unicode code points = 2

Sau NFC: U+00E9
  UTF-16 code units = 1
  Unicode code points = 1

Một chữ é người dùng thường nhận biết: 1 grapheme cluster
```

Nếu đang lưu offset con trỏ, ranh giới `substring`, vùng tô sáng, chỉ số tìm kiếm hay tọa độ ghi chú trên nội dung gốc, **không dùng lại chỉ số cũ sau khi chuẩn hóa**. Hãy chuẩn hóa trước khi tính offset hoặc xây cơ chế ánh xạ vị trí nguồn–đích khi cần giữ các tọa độ trên văn bản gốc.

## 7. Chuẩn hóa trước khi so sánh và tìm kiếm

`String.equals()`, `indexOf()`, `contains()` và khóa `String` trong `HashMap` không tự áp dụng Unicode normalization. Vì thế dữ liệu về cùng một từ nhưng có cách mã hóa dấu khác nhau có thể so sánh `false` hoặc không khớp khi tìm.

Quy trình phổ biến cho **tương đương chuẩn tắc**:

1. Xác định quy tắc so sánh: ở đây chấp nhận hai chuỗi *canonically equivalent* là cùng văn bản.
2. Chọn **một dạng duy nhất**, thường là NFC.
3. Chuẩn hóa **cả hai phía** trước khi so sánh hoặc khi ghi/tra cứu khóa.
4. Dùng `equals()`/`Objects.equals()` hoặc thao tác tìm kiếm trên chuỗi đã chuẩn hóa.

### Ví dụ 3: khóa `HashMap` phải có dạng nhất quán

Lưu thành **`NormalizedLookupDemo.java`**:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;

public class NormalizedLookupDemo {
    private static String nfc(String s) {
        return Normalizer.normalize(s, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String stored = "caf\u00E9";
        String queried = "cafe\u0301";

        Map<String, String> labels = new HashMap<>();
        labels.put(stored, "found");

        System.out.println("raw equals: " + stored.equals(queried));
        System.out.println("lookup raw: " + labels.get(queried));
        System.out.println("lookup NFC: " + labels.get(nfc(queried)));

        Map<String, String> canonical = new HashMap<>();
        canonical.put(nfc(stored), "normalized");
        System.out.println("canonical lookup: " + canonical.get(nfc(queried)));
    }
}
```

```bash
javac NormalizedLookupDemo.java
java NormalizedLookupDemo
```

**Stdout:**

```text
raw equals: false
lookup raw: null
lookup NFC: found
canonical lookup: normalized
```

Dòng `lookup NFC` thành công vì `stored` trong ví dụ đã ở NFC; **không thể tổng quát hóa** rằng chỉ chuẩn hóa phía truy vấn là đủ. Để tránh phụ thuộc vào việc phía lưu trữ tình cờ đã được chuẩn hóa, hãy dùng cùng một hàm `nfc(...)` khi **ghi khóa** và **tạo khóa tra cứu**, như `canonical` ở cuối ví dụ.

Một hệ thống đã có dữ liệu lưu theo nhiều dạng khác nhau cần kế hoạch **chuyển đổi dữ liệu** hoặc chiến lược tra cứu phù hợp. Chỉ thay đổi mã đọc có thể khiến các khóa cũ không thể tìm thấy nếu dạng chuẩn hóa của khóa lưu không đồng nhất.

### Tìm chuỗi con có dấu

Nếu muốn `contains()` hoặc `indexOf()` chấp nhận sự tương đương chuẩn tắc, có thể chuẩn hóa cả chuỗi nguồn và từ khóa về NFC trước khi tìm. Nhưng offset mà `indexOf()` trả về là offset UTF-16 **trên chuỗi đã chuẩn hóa**. Nếu cần dùng offset đó để đánh dấu **chuỗi nguồn chưa chuẩn hóa**, phải ánh xạ lại vị trí; không được đưa offset mới trực tiếp vào nguồn cũ.

Nếu ứng dụng cần tìm kiếm theo ngôn ngữ, bỏ phân biệt hoa/thường, xử lý biến thể dấu hoặc sắp xếp từ điển, chỉ NFC có thể không đủ; cần xác định thuật toán so khớp theo locale hoặc bộ máy tìm kiếm phù hợp.

## 8. Normalization và chuyển chữ hoa/thường là hai bước độc lập

NFC, NFD, NFKC, NFKD **không phải** các chế độ “lowercase” hay “case-insensitive”. Chẳng hạn:

```java
String a = "Java";
String b = "java";

System.out.println(java.text.Normalizer.normalize(
        a, java.text.Normalizer.Form.NFC).equals(b)); // false
```

Đây là **đoạn minh họa**, có thể chạy khi đặt trong một phương thức Java; kết quả in ra là `false`.

Nếu chính sách nghiệp vụ yêu cầu so sánh **không phân biệt chữ hoa/thường**, Java còn có `String.toLowerCase(Locale)`, `equalsIgnoreCase(...)` hoặc các API liên quan. Hãy chọn theo ngôn ngữ/ngữ cảnh:

- `toLowerCase(Locale.ROOT)` thuận tiện cho một số mã định danh có quy tắc **không phụ thuộc locale**, nhưng không phải lúc nào cũng tương đương thuật toán *full Unicode case folding*.
- `Locale` cụ thể có thể làm thay đổi cách chuyển hoa/thường đối với một số chữ, chẳng hạn tiếng Thổ Nhĩ Kỳ.
- Việc đổi hoa/thường có thể thay đổi dãy code point; nếu thiết kế yêu cầu dạng chuẩn hóa cố định sau biến đổi, hãy cân nhắc **chuẩn hóa lại sau bước đổi hoa/thường**.
- NFKC **không tự** thực hiện full case folding; khái niệm `NFKC_Casefold` trong một số tiêu chuẩn Unicode không đơn giản là lời gọi `Normalizer.normalize(s, NFKC)`.

Bởi vậy, không gọi NFKC rồi mặc định kết luận hai tên người, tên tài khoản hoặc chuỗi tiếng tự nhiên “bằng nhau bất kể hoa/thường”. Quy tắc so sánh cần được mô tả rõ và kiểm thử với các ngôn ngữ mà ứng dụng hỗ trợ.

## 9. Chọn dạng nào cho tình huống thực tế?

| Tình huống | Lựa chọn cân nhắc | Lý do và giới hạn |
|---|---|---|
| Muốn lưu/so sánh văn bản thông thường theo tương đương chuẩn tắc | **NFC** | Duy trì phân biệt tương thích trong khi thống nhất dạng dựng sẵn/tổ hợp |
| Thuật toán cần phân tích riêng ký tự cơ sở và dấu kết hợp | **NFD** | Phân rã chuẩn tắc để thao tác code point; tránh ngộ nhận rằng mọi dấu đều có thể loại bỏ tùy ý |
| Chuẩn hóa mã định danh với các ký tự tương thích theo đặc tả rõ ràng | **NFKC** | Có thể gộp chữ fullwidth, ligature, ký hiệu trình bày; cần chính sách chấp nhận các phép gộp |
| Xử lý từng phần tử sau phân rã tương thích | **NFKD** | Giữ phân rã tương thích để phân tích; có thể làm mất phân biệt biểu diễn |
| Văn bản pháp lý, bản chép chính xác, chữ ký số hoặc dữ liệu cần giữ byte gốc | **Không tự ý chuyển** | Chuẩn hóa có thể đổi code point và byte; chỉ làm khi giao thức/đặc tả quy định |
| Mật khẩu hoặc giá trị bí mật đưa vào KDF/hàm băm | **Theo đúng đặc tả xác thực** | Chuẩn hóa ngoài hợp đồng làm thay đổi giá trị xác thực và có thể gây không tương thích |
| Tìm kiếm nhạy theo ngôn ngữ, bỏ hoa/thường hoặc bỏ dấu | **Quy tắc tìm kiếm riêng** | Một dạng Normalizer đơn lẻ không đáp ứng trọn quy tắc ngôn ngữ |
| Cần hiển thị đồng nhất về mặt glyph/độ rộng | **Xử lý font và UI** | Normalization không kiểm soát cách renderer tạo hình glyph |

**NFC thường là lựa chọn nhất quán tương đối an toàn khi yêu cầu chỉ là canonical equivalence**, nhưng ngay cả NFC cũng có thể đổi dãy byte và offset. Không có một dạng chuẩn hóa “đúng nhất” cho mọi ứng dụng. NFKC/NFKD mạnh hơn theo nghĩa gộp thêm những khác biệt tương thích; “mạnh hơn” không đồng nghĩa “tốt hơn” cho mọi dữ liệu.

### Tránh tự động xóa dấu sau NFD

Một mẹo thường thấy là phân rã bằng NFD rồi xóa mọi ký tự có category *Mark* (ví dụ regex `\p{M}`). Cách này có thể khiến `"café"` trở thành `"cafe"`, nhưng đó là **thuật toán loại dấu riêng**, vượt ra ngoài normalization thuần túy. Với tiếng Việt và nhiều hệ chữ khác, dấu có thể mang ý nghĩa từ vựng và ngữ pháp; xóa dấu có thể tạo nhập nhằng hoặc sai nghĩa. Nếu cần tìm kiếm không dấu, nên thiết kế một chỉ mục/phép tìm kiếm riêng và vẫn giữ văn bản gốc.

## 10. Hiệu năng, phiên bản Unicode và tính ổn định

- Chuẩn hóa có chi phí duyệt/biến đổi nội dung. Với dữ liệu lớn hoặc đường đi xử lý nóng, tránh chuẩn hóa cùng một chuỗi không đổi nhiều lần nếu có thể tổ chức quy trình chuẩn hóa một lần ở ranh giới tiếp nhận/lưu dữ liệu.
- `isNormalized(...)` hỗ trợ phát hiện chuỗi đã đúng dạng, nhưng việc kiểm tra cũng phải đọc dữ liệu; không mặc định một lời gọi kiểm tra cộng một lời gọi chuẩn hóa luôn nhanh hơn việc chuẩn hóa trực tiếp. Khi hiệu năng là yêu cầu, đo bằng benchmark trên workload đại diện.
- Các API Java chuẩn trả kết quả tuân theo dữ liệu Unicode do JDK triển khai. Bộ dữ liệu và hỗ trợ ký tự có thể được cập nhật khi nâng JDK; nếu hệ thống trao đổi dữ liệu giữa nhiều runtime, hãy kiểm tra các ký tự quan trọng và chính sách cập nhật.
- Unicode normalization có các bảo đảm về **tính ổn định chuẩn hóa** theo quy tắc chuẩn, nhưng điều đó không có nghĩa mọi phiên bản JDK nhận biết mọi ký tự Unicode mới như nhau, hoặc mọi hành vi tìm kiếm/hiển thị đều đồng nhất.
- Luôn ghi rõ dạng chuẩn hóa ở các ranh giới dữ liệu quan trọng: ví dụ “khóa được lưu và truy vấn ở NFC” dễ kiểm chứng hơn quy tắc ngầm hiểu.
- Không dùng `==` để so nội dung sau chuẩn hóa: hai kết quả có cùng dãy ký tự không bắt buộc là cùng đối tượng `String`. Dùng `equals()` hoặc `Objects.equals()`.

## 11. Các lỗi phổ biến

| Hiểu nhầm hoặc lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| `"é".equals("e\u0301")` phải `true` vì trông giống | `equals()` so chuỗi code unit, không tự chuẩn hóa | Chọn NFC/NFD và chuẩn hóa hai bên khi cần canonical equivalence |
| NFC là “xóa dấu” | NFC có thể ghép dấu vào ký tự dựng sẵn | Dùng NFC cho dạng ghép chuẩn tắc, không coi là lọc dấu |
| NFD luôn tạo một code point cho mỗi chữ | NFD là phân rã, có thể tạo nhiều code point | Phân biệt code unit, code point và grapheme cluster |
| NFC/NFD và NFKC/NFKD luôn tương đương | Các dạng có K còn thực hiện phân rã tương thích | Chọn dạng dựa trên quy tắc nghiệp vụ |
| NFKC không ảnh hưởng nội dung quan trọng | `①` thành `1`, `ﬃ` thành `ffi` có thể mất sự phân biệt cần thiết | Không mặc định NFKC cho dữ liệu cần bảo toàn khác biệt |
| Chỉ chuẩn hóa đầu vào truy vấn | Khóa lưu có thể ở dạng khác | Chuẩn hóa nhất quán tại lúc lưu và lúc tìm |
| Chuẩn hóa làm `indexOf` trên nguồn cũ đúng offset | Độ dài/code point có thể thay đổi | Tính offset trên đúng chuỗi đích hoặc ánh xạ vị trí |
| Chuẩn hóa tự giải quyết hoa/thường | Normalizer không thực hiện case folding chung | Thiết kế bước xử lý hoa/thường riêng |
| Dùng `==` để so hai chuỗi đã chuẩn hóa | `==` là so tham chiếu | Dùng `equals()` cho nội dung |
| Chuẩn hóa tự loại ký tự gây nhầm lẫn hoặc làm sạch input nguy hiểm | Unicode confusables, kiểm tra dữ liệu và an toàn đầu vào là các vấn đề khác | Dùng quy tắc xác thực riêng, không coi Normalizer là bộ lọc an toàn |
| Chuẩn hóa mà bỏ kết quả trả về | `String` là immutable | Gán lại biến hoặc dùng giá trị trả về |

## 12. Tự kiểm tra

Trước khi chạy, dự đoán các giá trị bên dưới:

**`NormalizationSelfCheck.java`**

```java
import java.text.Normalizer;

public class NormalizationSelfCheck {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        System.out.println(a.equals(b));
        System.out.println(Normalizer.normalize(a, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(b, Normalizer.Form.NFC)));

        String circledOne = "\u2460";
        String plainOne = "1";

        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFC).equals(plainOne));
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFKC).equals(plainOne));

        String mixedCase = "Java";
        System.out.println(Normalizer.normalize(
                mixedCase, Normalizer.Form.NFKC).equals("java"));
    }
}
```

```bash
javac NormalizationSelfCheck.java
java NormalizationSelfCheck
```

**Stdout:**

```text
false
true
false
true
false
```

Giải thích:

1. `a` và `b` chưa chuẩn hóa bằng nhau về hiển thị, nhưng `String.equals()` trực tiếp vẫn là `false`.
2. Cùng đưa về NFC, cả hai trở thành dãy code point tương đương chuẩn tắc, nên kết quả `equals()` là `true`.
3. NFC không áp dụng ánh xạ tương thích `①` → `1`, nên `false`.
4. NFKC có ánh xạ tương thích ấy, vì vậy `true`.
5. NFKC không đổi `J` hoa thành `j` thường, nên chuỗi `"Java"` vẫn khác `"java"`.

**Câu hỏi để tự chọn dạng:** ứng dụng của bạn cần bảo toàn mọi ký hiệu tương thích và chỉ thống nhất các biểu diễn chuẩn tắc (NFC/NFD), hay chấp nhận gộp một số ký tự trình bày về chữ/số thông thường (NFKC/NFKD)? Bước tiếp theo là chọn dạng có cơ sở, chuẩn hóa nhất quán ở các ranh giới dữ liệu, rồi so sánh bằng `equals()` và kiểm thử dữ liệu Unicode đại diện.
