# NFC, NFD, NFKC và NFKD: Unicode Normalization trong Java

## 1. Vì sao văn bản nhìn giống nhau lại so sánh khác?

Unicode định nghĩa các **code point** cho ký tự. Một số chữ có thể lưu bằng các chuỗi code point khác nhau nhưng vẫn được coi là tương đương theo Unicode. Chẳng hạn, chữ `é` có hai biểu diễn thông dụng:

```text
U+00E9             é        (một code point dựng sẵn)
U+0065 U+0301      e + ◌́    (e cộng COMBINING ACUTE ACCENT)
```

Màn hình có thể hiển thị chúng gần như giống hệt, nhưng trong Java:

```java
String a = "\u00E9";
String b = "e\u0301";
System.out.println(a.equals(b)); // false
```

`String.equals` kiểm tra chuỗi UTF-16 code units, không tự áp dụng một quan hệ tương đương Unicode. Nếu ứng dụng lưu nickname, tìm kiếm tên người, so khớp tiêu đề hoặc quản lý khóa dữ liệu lấy từ nhiều bộ gõ/nguồn import, sự khác biệt này có thể dẫn đến kết quả bất ngờ.

**Unicode normalization** là quá trình chuyển văn bản về một biểu diễn chuẩn theo quy tắc thống nhất. Chuẩn Unicode hiện hành định nghĩa **bốn normalization forms** — **NFC, NFD, NFKC và NFKD** — trong Unicode Standard Annex #15 (UAX #15). Cả bốn đều được JDK 17+ hỗ trợ bằng `java.text.Normalizer`.

Sau bài này, bạn sẽ:
1. Phân biệt **canonical equivalence** và **compatibility equivalence**.
2. Hiểu chính xác sự khác nhau giữa bốn forms.
3. Sử dụng `Normalizer.normalize` và `Normalizer.isNormalized` với Java 17+.
4. Quan sát các ví dụ chữ có dấu tiếng Việt, ligature, số khoanh tròn và fullwidth.
5. Thiết kế quy tắc chuẩn hóa cho lưu trữ, so sánh, tìm kiếm và identifiers.
6. Tránh nhầm normalization với bỏ dấu, đổi hoa/thường, grapheme segmentation hoặc giải pháp bảo mật toàn diện.

## 2. Hai quan hệ tương đương của Unicode

### 2.1. Canonical equivalence

Hai chuỗi **canonically equivalent** biểu diễn cùng một nội dung ký tự ở mức trừu tượng theo chuẩn Unicode, dù có các biểu diễn code point khác nhau. Ví dụ:

```text
U+00E9                    é
U+0065 U+0301             e + dấu sắc

U+1EAF                    ắ
U+0061 U+0306 U+0301      a + dấu breve + dấu sắc
```

Khi cả hai biểu diễn của một cặp được chuẩn hóa **cùng một form NFC** hoặc **cùng một form NFD**, kết quả sẽ giống nhau về chuỗi code point. Unicode còn quy định cách sắp xếp lại **combining marks** theo canonical combining class để đạt trật tự chuẩn.

Lưu ý: NFD không đơn thuần là “tách mọi chữ thành chữ ASCII và một dấu”; chữ và dấu có thể phân rã thành nhiều code point, có quy tắc thứ tự riêng và không phải mọi ký tự đều có canonical decomposition.

### 2.2. Compatibility equivalence

Một số ký tự Unicode tồn tại để phân biệt kiểu chữ, ký pháp, độ rộng hoặc cách trình bày. Chúng không nhất thiết có cùng canonical value với dạng chữ thường, nhưng có **compatibility mapping**. Ví dụ:

| Ký tự | Code point | Compatibility decomposition | Phân biệt có thể mất |
| --- | --- | --- | --- |
| `ﬃ` | `U+FB03` | `ffi` | Ligature/kiểu chữ ghép |
| `①` | `U+2460` | `1` | Số có vòng tròn |
| `Ａ` | `U+FF21` | `A` | Độ rộng fullwidth |
| `²` | `U+00B2` | `2` | Ký hiệu chỉ số trên |

**Đây là khác biệt có thể mang ý nghĩa.** Trong tài liệu toán học, `x²` và `x2` không nhất thiết có cùng nghĩa. Vì vậy, việc NFKC/NFKD gộp chúng có thể phù hợp với **khóa tìm kiếm** nhưng không phù hợp để **thay thế văn bản gốc**. Không được coi compatibility normalization là một phép biến đổi vô hại cho mọi loại dữ liệu.

## 3. Bảng phân biệt NFC, NFD, NFKC và NFKD

| Form | Tên | Thuật toán khái quát | Tương đương được thống nhất | Nên cân nhắc khi |
| --- | --- | --- | --- | --- |
| **NFD** | Normalization Form D | **Canonical decomposition** và sắp xếp marks theo quy tắc Unicode | Canonical | Xử lý/khảo sát chuỗi phân rã hoặc dấu kết hợp |
| **NFC** | Normalization Form C | Canonical decomposition, sau đó **canonical composition** | Canonical | Văn bản thông thường, canonical equality, normalized lookup key |
| **NFKD** | Normalization Form KD | **Compatibility decomposition**, cũng bao gồm canonical decomposition | Compatibility | Quy trình phân tích/so khớp có chủ đích loại phân biệt compatibility |
| **NFKC** | Normalization Form KC | Compatibility decomposition, sau đó canonical composition | Compatibility | Identifier preparation hoặc so khớp rộng hơn khi contract cho phép |

Cách nhớ:
- **D** là *decomposition* — phân rã.
- **C** là *composition* — tạo dạng tổ hợp theo quy tắc canonical.
- **K** chỉ *compatibility*, phân biệt với normalization chỉ xét canonical equivalence.

Các forms có tính chất **idempotent**: chuẩn hóa một chuỗi nhiều lần với **cùng form** sẽ có kết quả giống một lần. Tuy nhiên, một form không nhất thiết tạo **ít code point nhất**; algorithm còn có các điều kiện về combining class, composition exclusion và các mapping khác.

### 3.1. Ví dụ đối chiếu

| Input | NFC | NFD | NFKC | NFKD |
| --- | --- | --- | --- | --- |
| `e + ◌́` | `é` | `e + ◌́` | `é` | `e + ◌́` |
| `é` | `é` | `e + ◌́` | `é` | `e + ◌́` |
| `ﬃ` | `ﬃ` | `ﬃ` | `ffi` | `ffi` |
| `①` | `①` | `①` | `1` | `1` |
| `Ａ` | `Ａ` | `Ａ` | `A` | `A` |
| `ắ` | `ắ` | `a + ◌̆ + ◌́` | `ắ` | `a + ◌̆ + ◌́` |

Nếu không có **compatibility mapping**, việc thêm K thường không làm thay đổi một ví dụ canonical cụ thể. Nhưng khi có compatibility distinction (như `①`), NFC/NFD giữ phân biệt đó còn NFKC/NFKD có thể xóa.

## 4. API Java chuẩn: java.text.Normalizer

JDK 17+ cung cấp sẵn các API:

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;

String canonicalComposed =
        Normalizer.normalize(input, Form.NFC);
String canonicalDecomposed =
        Normalizer.normalize(input, Form.NFD);
String compatibilityComposed =
        Normalizer.normalize(input, Form.NFKC);
String compatibilityDecomposed =
        Normalizer.normalize(input, Form.NFKD);

boolean alreadyNfc =
        Normalizer.isNormalized(input, Form.NFC);
```

Đây là **snippet** ở trong một method đã có biến `input` kiểu `String`.

- `Normalizer.normalize(CharSequence, Normalizer.Form)` nhận chuỗi và một form, **trả String** đã chuẩn hóa.
- `Normalizer.isNormalized(CharSequence, Normalizer.Form)` trả `boolean` xác định chuỗi có ở form đó không.
- `Normalizer.Form` là enum chứa `NFC`, `NFD`, `NFKC`, `NFKD`.
- Lớp thuộc **`java.base`**, không cần thêm dependency bên ngoài.

`String` trong Java là immutable; `normalize` **không biến đổi String đầu vào**. Nếu muốn lưu giá trị đã chuẩn hóa, phải dùng kết quả trả về:

```java
String normalized = Normalizer.normalize(original, Form.NFC);
```

Không dựa vào giá trị `original` để giả định đã được thay đổi. Với input có thể null, hãy xử lý `null` theo chính sách ứng dụng trước khi gọi; không dựa vào hành vi “null sẽ trở thành chuỗi rỗng”.

## 5. Ví dụ Java 17+ đầy đủ với stdout đã kiểm chứng

Trong nhiều font, ký tự ghép và ký tự dựng sẵn nhìn giống nhau. Chúng ta sẽ in **code point dạng U+XXXX** để thấy chính xác.

Tạo file **`UnicodeNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public final class UnicodeNormalizationDemo {

    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String label, String value) {
        System.out.println(label + "=" + codePoints(value));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(
                "rawEqual=" + composed.equals(decomposed));
        System.out.println(
                "nfcEqual=" +
                Normalizer.normalize(composed, Form.NFC).equals(
                        Normalizer.normalize(decomposed, Form.NFC)));

        show("NFC(e+acute)",
                Normalizer.normalize(decomposed, Form.NFC));
        show("NFD(e-acute)",
                Normalizer.normalize(composed, Form.NFD));

        show("NFC(ligature)",
                Normalizer.normalize("\uFB03", Form.NFC));
        show("NFKC(ligature)",
                Normalizer.normalize("\uFB03", Form.NFKC));

        show("NFD(circled)",
                Normalizer.normalize("\u2460", Form.NFD));
        show("NFKD(circled)",
                Normalizer.normalize("\u2460", Form.NFKD));

        show("NFKC(fullwidth)",
                Normalizer.normalize("\uFF21", Form.NFKC));
        show("NFD(vietnamese)",
                Normalizer.normalize("\u1EAF", Form.NFD));

        System.out.println(
                "isNFC(Vietnamese)=" +
                Normalizer.isNormalized("\u1EAF", Form.NFC));
        System.out.println(
                "isNFD(Vietnamese)=" +
                Normalizer.isNormalized("\u1EAF", Form.NFD));
    }
}
```

Lưu source bằng UTF-8, biên dịch và chạy trong terminal có JDK 17 trở lên:

```bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

**Stdout chính xác** của đoạn code trên với JDK được kiểm thử:

```text
rawEqual=false
nfcEqual=true
NFC(e+acute)=U+00E9
NFD(e-acute)=U+0065 U+0301
NFC(ligature)=U+FB03
NFKC(ligature)=U+0066 U+0066 U+0069
NFD(circled)=U+2460
NFKD(circled)=U+0031
NFKC(fullwidth)=U+0041
NFD(vietnamese)=U+0061 U+0306 U+0301
isNFC(Vietnamese)=true
isNFD(Vietnamese)=false
```

**Giải thích:**
1. `rawEqual=false` do hai chuỗi `é` có biểu diễn mã khác nhau.
2. `nfcEqual=true` vì cả hai được đưa về canonical composed `U+00E9`.
3. NFD chuyển `é` thành `U+0065 U+0301`.
4. NFC giữ nguyên ligature `ﬃ` (`U+FB03`), nhưng NFKC biến thành `U+0066 U+0066 U+0069`, tức `ffi`.
5. NFD giữ `①` nhưng NFKD biến thành `1`; NFKC chuyển fullwidth A thành ASCII A.
6. NFD của chữ tiếng Việt `ắ` (`U+1EAF`) thành `U+0061 U+0306 U+0301`. Đây là **tách dấu**, không phải **bỏ dấu**.
7. Chữ `ắ` dựng sẵn đã ở NFC nhưng chưa ở NFD, vì vậy hai dòng `isNormalized` trả khác nhau.

**Lưu ý về Java source:** `\u00E9` và các đoạn tương tự là Unicode escapes để biểu diễn code point rõ ràng; chương trình không phụ thuộc bàn phím có gõ được glyph hay không. Phương thức `String.codePoints()` duyệt Unicode code points thay vì từng UTF-16 `char`; điều này quan trọng cho các ký tự ngoài Basic Multilingual Plane.

## 6. Chuẩn hóa tiếng Việt: giữ nguyên nghĩa, không bỏ dấu

Tiếng Việt có nhiều ký tự kết hợp dấu, như `ắ`, `ầ`, `ễ`, `ộ`. Một số nguồn lưu chữ dựng sẵn, nguồn khác lưu chữ cơ sở và dấu kết hợp. Ví dụ:

```java
String precomposed = "\u1EAF";   // ắ
String decomposed = "a\u0306\u0301";

boolean rawEqual = precomposed.equals(decomposed);
boolean normalizedEqual =
        Normalizer.normalize(precomposed, Form.NFC)
                .equals(Normalizer.normalize(decomposed, Form.NFC));
```

Đây là snippet có import `java.text.Normalizer` và `Normalizer.Form`. `rawEqual` là `false`, còn `normalizedEqual` là `true`.

**NFC** thường là lựa chọn hợp lý cho văn bản thông thường cần **canonical equality** mà vẫn bảo toàn dấu. Nhưng form cụ thể vẫn phải do giao thức, sản phẩm hoặc cơ sở dữ liệu quyết định. Không mặc định thay thế toàn bộ văn bản đã lưu trong một hệ thống cũ nếu chưa kiểm tra tác động tới khóa, sort order và dữ liệu lịch sử.

### 6.1. NFD không có nghĩa bỏ dấu

NFD chuyển `ắ` thành `a + breve + acute`, chứ không thành `a`. Trên Internet có thể gặp cách bỏ combining marks sau NFD:

```java
// Không áp dụng mặc định lên mọi văn bản tiếng Việt:
String stripped = Normalizer.normalize(text, Form.NFD)
        .replaceAll("\\p{M}+", "");
```

Đây là snippet với biến `text`. Cách này có thể xóa những dấu mang nghĩa ngôn ngữ: `ma`, `má`, `mà`, `mạ` là các từ khác nhau. Ngoài ra, regex `\\p{M}` chỉ nhắm đến category mark, **không bảo đảm** chuyển mọi chữ/ký hiệu Unicode về ASCII hoặc tạo chức năng search ngôn ngữ đúng. Nếu cần tìm kiếm không dấu, hãy tạo **chỉ mục tìm kiếm phụ** với policy riêng, đừng ghi đè nội dung gốc.

### 6.2. Canonical ordering của các dấu

Unicode quy định thứ tự chuẩn của combining marks theo **canonical combining class**. Khi có nhiều dấu, việc sắp xếp theo trật tự tương đương canonical có thể là một phần của normalization. Vì thế:
- Không tự ghép/tách dấu bằng việc dò từng `char` theo thứ tự nhập.
- Không giả định mọi chuỗi có thể rút còn một code point dựng sẵn.
- Không normalize riêng từng dấu hoặc từng đoạn cắt tùy ý, rồi nối, vì có thể bỏ qua tương tác giữa dấu và ký tự cơ sở qua ranh giới đoạn.

Nên chuẩn hóa **chuỗi hoàn chỉnh** hoặc sử dụng thuật toán streaming Unicode được thiết kế đúng chuẩn khi cần xử lý dữ liệu lớn.

## 7. Chuẩn hóa để so sánh và dùng làm key

Khi nghiệp vụ muốn coi các chuỗi **canonically equivalent** là bằng nhau, chuẩn hóa **cả hai phía** theo cùng form:

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Objects;

static String canonicalKey(String input) {
    Objects.requireNonNull(input, "input");
    return Normalizer.normalize(input, Form.NFC);
}

static boolean sameCanonicalText(String left, String right) {
    return canonicalKey(left).equals(canonicalKey(right));
}
```

Đây là các phương thức static trong một class, không phải chương trình độc lập. Chính sách `Objects.requireNonNull` có chủ đích: null được coi là dữ liệu không hợp lệ, không bị âm thầm chuyển thành rỗng.

Với `HashMap<String, ...>`, database unique key hay cache:
- `String.equals` và `hashCode` **không tự normalization**.
- Nếu lưu `canonicalKey(input)`, phải chuẩn hóa cả `lookupInput` khi tra cứu.
- Nếu đã có dữ liệu trước khi thêm normalization, hãy kiểm tra **collision**: hai khóa trước đây khác nhau có thể trở thành cùng một khóa.
- Nếu sản phẩm cần giữ đúng chữ người dùng nhập, có thể lưu riêng **original text** cho UI và **normalized key** cho đối chiếu.
- Không dùng NFKC chỉ vì “dữ liệu sẽ sạch hơn” nếu sự khác biệt giữa `①` và `1` là một phần hợp lệ của domain.

**Ví dụ collision:** hai username `"①"` và `"1"` là khác nhau ở raw strings; dưới NFKC chúng có thể đều trở thành `"1"`. Migration phải kiểm tra các trường hợp như vậy trước khi thay đổi unique index hoặc chính sách đăng nhập.

## 8. NFKC cho identifiers và rủi ro bảo mật

NFKC có ích trong một số **identifier profiles** muốn gộp những dạng chữ tương đương ở mức compatibility. Ví dụ:

```java
String prepared = Normalizer.normalize(rawIdentifier, Form.NFKC);
```

Đây là snippet. Bản thân NFKC **không đủ** tạo một bộ quy tắc identifier hoàn chỉnh. Một hệ thống thực tế còn phải quyết định:
- Cho phép những tập code point/script nào?
- Có phân biệt chữ hoa và chữ thường không?
- Có hỗ trợ username trộn nhiều hệ chữ không?
- Có kiểm tra ký tự điều khiển/formatting hoặc độ dài không?
- Khi hai chuỗi chuẩn hóa thành cùng key thì ứng dụng xử lý thế nào?
- Dữ liệu cũ sẽ được migration, phát hiện trùng và audit ra sao?

**NFKC không phải Unicode confusable detector.** Chữ `a` Latin và chữ `а` Cyrillic có thể trông gần giống nhưng không tự biến thành cùng một chữ bằng NFC/NFKC. Để chống spoofing, cần đánh giá chính sách script, confusable detection theo hướng dẫn bảo mật Unicode và cách hiển thị UI.

**Không dùng normalization thay cho input validation hoặc escaping**: NFC/NFKC không tự ngăn SQL injection, XSS, Unicode spoofing hay mọi lỗi mã hóa. Sử dụng parameterized query, output encoding và validation theo context.

### 8.1. Mật khẩu và token

Đừng tự động áp dụng NFKC lên mật khẩu đang dùng trong một hệ thống nếu chính sách xác thực ban đầu không làm thế. Việc âm thầm đổi normalization có thể khiến người dùng không đăng nhập được hoặc làm hai input khác nhau trở thành cùng chuỗi. Nếu một giao thức xác thực có **Unicode preparation** riêng, các bên phải dùng cùng quy tắc và có migration plan khi thay đổi.

`Normalizer` chỉ chuyển biểu diễn text, **không mã hóa, không hash, không xác thực** và không bảo vệ dữ liệu bí mật trong bộ nhớ. Vòng đời password/token và hệ thống verifier phải được thiết kế riêng.

## 9. Normalization khác case folding, tìm kiếm và collation

| Nhu cầu | `Normalizer` có đáp ứng đầy đủ không? | Giải pháp bổ sung |
| --- | --- | --- |
| Tương đương canonical của `é` | Có — cùng NFC hoặc NFD | So sánh normalized strings |
| Gộp `Ａ` với `A` | Có — NFKC/NFKD | Policy compatibility |
| Gộp `A` và `a` | **Không** | Case mapping/case folding hoặc collation theo yêu cầu |
| Tìm kiếm `ma` khớp `má` | **Không** | Accent-insensitive search index có quy tắc riêng |
| Sắp xếp từ ngữ theo locale | **Không** | `java.text.Collator` hoặc collation DB phù hợp |
| Phát hiện mọi ký tự giả mạo | **Không** | Script/confusable checks, policy identifier |
| Phân đoạn ký tự để di chuyển con trỏ UI | **Không** | Unicode grapheme segmentation phù hợp |

`String.equalsIgnoreCase(...)` cũng không phải phép thay thế hoàn chỉnh cho Unicode normalization và Unicode case folding của mọi ngôn ngữ. Không dùng một thao tác “normalize rồi lowercase” làm bộ tìm kiếm ngôn ngữ phổ quát khi sản phẩm cần hành vi locale-aware rõ ràng.

## 10. UTF-16 code units, code points và grapheme clusters

Java `String` lưu văn bản theo UTF-16. Có ba cách đếm cần phân biệt:

1. **Code units:** `String.length()` đếm số đơn vị `char` (UTF-16), không phải số ký tự người dùng nhìn thấy.
2. **Code points:** `String.codePoints()` / `codePointCount(...)` đếm các code point. Một ký tự ngoài BMP có thể chiếm hai UTF-16 code units.
3. **Grapheme clusters:** đơn vị ký tự theo cảm nhận người dùng, có thể gồm nhiều code points như chữ và các dấu kết hợp hoặc emoji sequence.

Ví dụ chữ `ắ` dựng sẵn là một code point `U+1EAF`; dạng NFD ví dụ gồm ba code point `U+0061 U+0306 U+0301`. **Hai biểu diễn vẫn có thể hiển thị thành một cụm chữ duy nhất** nhưng `length()` khác nhau. NFC không hứa mỗi grapheme chỉ có một `char`.

Nếu ứng dụng cần giới hạn “số ký tự người dùng thấy”, xử lý cursor trong editor, cắt chuỗi hoặc phân đoạn emoji, phải dùng segmentation theo Unicode, không chỉ đếm `length()` hoặc gọi `Normalizer`.

## 11. Kiểm tra form, tính idempotent và hiệu năng

Kiểm tra một chuỗi đã ở dạng chuẩn chưa:

```java
boolean ready = Normalizer.isNormalized(value, Form.NFC);
```

Đây là snippet với `value` kiểu `String`. `isNormalized` hữu ích khi muốn **validate invariant** (ví dụ API chỉ chấp nhận NFC), hoặc khi cần test dữ liệu nhập. Nếu mục tiêu chỉ là **lấy kết quả chuẩn**, gọi thẳng `normalize` thường đủ; không cần thiết luôn quét một lượt `isNormalized` rồi quét tiếp `normalize`.

Tính idempotent:

```java
String once = Normalizer.normalize(value, Form.NFC);
String twice = Normalizer.normalize(once, Form.NFC);
boolean unchanged = once.equals(twice);
```

Với cùng form, `unchanged` là true theo tính chất normalization. Tuy nhiên, không nên gọi normalize ở mọi tầng nếu đã có invariant rõ tại ingestion boundary: điều này tạo công việc lặp lại, tăng chi phí và khiến policy khó kiểm soát.

### 11.1. Không chuẩn hóa từng char độc lập

Combining marks có quan hệ với ký tự lân cận. Thao tác normalize từng `char` hoặc từng phần được cắt bất kỳ rồi nối kết quả **không nhất thiết giống normalize toàn bộ chuỗi**. Với dữ liệu streaming lớn, sử dụng thuật toán incremental/stream-safe đúng chuẩn, không cắt ngẫu nhiên trong surrogate pair hoặc giữa một nhóm dấu và chữ cơ sở.

### 11.2. Unicode version trong JDK

`java.text.Normalizer` dùng dữ liệu Unicode của implementation JDK. Không suy rằng Java 17 có mọi code point/mapping của Unicode release mới nhất. Khi đổi phiên bản JDK, cần kiểm tra Unicode data version, regression cases và các key dữ liệu được trao đổi xuyên hệ thống. Unicode UAX #15 có chính sách **stability** cho normalized forms, nhưng một runtime cũ không thể biết tất cả dữ liệu ký tự chưa có lúc nó phát hành.

Trong hệ thống lớn, ghi rõ normalization policy, form và compatibility assumptions; kiểm thử các trường hợp biên khi nâng compiler/runtime hoặc đổi thư viện Unicode.

## 12. Các lỗi thường gặp

| Lỗi / triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tên có dấu nhìn giống nhưng `equals` false | Hai biểu diễn canonically equivalent khác code points | Chuẩn hóa cùng NFC/NFD trước so sánh |
| NFD không đổi `①` thành `1` | Đây là compatibility mapping | Dùng NFKC/NFKD khi domain cho phép |
| NFC không đổi `ﬃ` thành `ffi` | Ligature có compatibility mapping, không phải canonical mapping tương ứng | Chọn NFKC/NFKD có chủ đích |
| NFKC làm trùng username | Compatibility distinctions bị gộp | Audit và xử lý collisions |
| NFD rồi tưởng tiếng Việt mất dấu | Decomposition vẫn giữ combining marks | Không gộp normalization với accent stripping |
| Chuẩn hóa nhưng chữ hoa/thường vẫn khác | Normalization không làm case folding | Quy định case/collation riêng |
| `String.length()` sai số chữ nhìn thấy | Đếm UTF-16 code units | Dùng đúng code point/grapheme logic |
| Normalization xong mà ký tự giả mạo vẫn tồn tại | Confusables không nhất thiết Unicode equivalent | Có chính sách script/confusable |
| Chia text thành nhiều đoạn rồi normalize riêng | Mất context combining marks hoặc tách surrogate pair | Normalize cả chuỗi hoặc dùng thuật toán streaming chuẩn |
| Dữ liệu import bị lỗi dấu dù normalize | Dữ liệu đã decode sai charset | Xác định UTF-8/charset đúng trước normalization |
| DB lookup không khớp sau migration | Input ghi và lookup dùng khác form | Thống nhất contract trên mọi đường |
| Dùng form mới cho password làm login fail | Thay đổi input chuẩn hóa làm credential khác | Tuân thủ giao thức xác thực và migration |
| Kết quả chuyển đổi khác giữa các môi trường | Runtime/Unicode dataset hoặc pipeline khác | Pin/test runtime và policy |

## 13. Bài tập tự kiểm tra

**Câu 1:** `"\u00E9".equals("e\u0301")` vì sao false và sau NFC lại true?

**Đáp án:** Vì raw strings có code units khác nhau, nhưng chúng canonically equivalent và trở về cùng biểu diễn NFC.

**Câu 2:** Form nào đưa `ﬃ` thành `ffi`?

**Đáp án:** NFKC hoặc NFKD; NFC/NFD không thực hiện compatibility decomposition tương ứng.

**Câu 3:** NFD có xóa dấu tiếng Việt không?

**Đáp án:** Không. Nó đưa chữ về canonical decomposition, vẫn giữ dấu kết hợp.

**Câu 4:** Vì sao không mặc định chuyển mọi chuỗi sang NFKC trước khi lưu?

**Đáp án:** NFKC có thể làm mất phân biệt hợp lệ như số khoanh tròn, chỉ số trên hoặc độ rộng; nó còn có thể gây collisions cho identifiers.

**Câu 5:** NFKC có ngăn hoàn toàn phishing/homograph attacks không?

**Đáp án:** Không. Những ký tự trông giống từ hệ chữ khác nhau có thể không có quan hệ compatibility equivalence; cần policy và confusable detection riêng.

**Câu 6:** Có thể lấy số “ký tự người dùng nhìn thấy” bằng `Normalizer.normalize(s,NFC).length()` không?

**Đáp án:** Không. `String.length()` vẫn đếm UTF-16 code units; grapheme clusters cần quy tắc phân đoạn riêng.

**Câu 7:** Khi lưu key đã NFC, khi tìm key cần làm gì?

**Đáp án:** Chuẩn hóa input tra cứu bằng cùng policy/form trước khi so sánh hoặc truy vấn.

**Câu 8:** `Normalizer.isNormalized(s, Form.NFC)` và `Normalizer.normalize(s, Form.NFC)` khác nhau ra sao?

**Đáp án:** `isNormalized` trả boolean kiểm tra trạng thái; `normalize` trả text đã chuẩn hóa.

## 14. Checklist khi áp dụng

- **Xác định miền dữ liệu**: văn bản hiển thị, identifier, search key, mật khẩu hoặc tài liệu cần bảo toàn ký pháp.
- **Chọn form phù hợp**: NFC/NFD cho canonical; NFKC/NFKD khi chủ ý gộp compatibility.
- **Decode đúng charset trước**; normalization không sửa lỗi decoding.
- **Chuẩn hóa tại boundary**, dùng cùng policy khi ghi và đọc.
- **Giữ original text khi cần**; normalized key không phải lúc nào cũng là văn bản tốt nhất để hiển thị.
- **Kiểm tra collision và migration** trước khi đổi form đối với dữ liệu đã có.
- **Tách normalization khỏi** case folding, accent stripping, collation, grapheme segmentation và security checks.
- **Viết test code points** bên cạnh test UI để nhận ra chuỗi nhìn giống nhưng mã khác nhau.
- **Kiểm thử với JDK/runtime thực** nếu có yêu cầu ổn định khi dữ liệu Unicode thay đổi.

## 15. Tài liệu chính thức, hiện còn áp dụng

- [Java SE 17 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) — `normalize` và `isNormalized`.
- [Java SE 17 — Normalizer.Form](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.Form.html) — bốn form chuẩn.
- [Java SE 25 — Normalizer.Form](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.Form.html) — API vẫn được hỗ trợ trong JDK hiện đại.
- [Unicode Consortium — UAX #15](https://www.unicode.org/reports/tr15/) — định nghĩa canonical/compatibility equivalence, thuật toán, tính ổn định.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html) — lựa chọn form cho từng loại dữ liệu.
