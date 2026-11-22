# Unicode: Kiểm tra isNormalized và thực hiện normalize trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu vì sao hai `String` trông giống nhau có thể có dãy Unicode code points khác nhau và `String.equals(...)` trả `false`.
- Dùng chính xác hai API hiện hành của `java.text.Normalizer`: `isNormalized(CharSequence, Normalizer.Form)` và `normalize(CharSequence, Normalizer.Form)`.
- Phân biệt bốn dạng chuẩn hóa Unicode **NFC, NFD, NFKC, NFKD**, chọn dạng phù hợp với yêu cầu lưu trữ, so sánh và tìm kiếm.
- Viết code Java 17+ kiểm tra trước khi chuẩn hóa, so sánh hai chuỗi sau chuẩn hóa, kiểm tra tính **idempotent** và quan sát sự khác nhau bằng Unicode code points.
- Nhận diện những điều **normalization không làm**: không tự xóa dấu tiếng Việt, không đổi chữ hoa/thường, không đồng nhất ký tự nhìn giống nhau, không tạo hàng rào bảo mật chống Unicode spoofing.
- Xử lý đúng những bẫy thực tế như **nối hai đoạn đã NFC nhưng chuỗi cuối chưa NFC**, chọn nhầm compatibility form và chuẩn hóa không nhất quán giữa các tầng hệ thống.

**Phạm vi:** Java Unicode text normalization trong module chuẩn `java.base`. `java.text.Normalizer` và bốn `Normalizer.Form` đều là **API hiện hành**, được Oracle Java SE 26 tài liệu hóa. Bài dùng kỹ thuật vẫn được áp dụng hiện nay, không hướng dẫn API hoặc giải pháp đã lỗi thời.

## 1. Vấn đề: “nhìn giống nhau” không đồng nghĩa “cùng dãy ký tự”

Trong Unicode, cùng một chữ có dấu có thể tồn tại dưới các dạng mã hóa khác nhau.

Ví dụ chữ **é**:

- **Dạng dựng sẵn (precomposed):** `U+00E9` — LATIN SMALL LETTER E WITH ACUTE.
- **Dạng tách (decomposed):** `U+0065` (LATIN SMALL LETTER E) theo sau `U+0301` (COMBINING ACUTE ACCENT).

Khi hiển thị bằng một font thích hợp, hai dãy thường trông như cùng một chữ. Nhưng trong Java:

```java
String composed = "caf\u00E9";
String decomposed = "cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
```

Đây là **đoạn minh họa**, không phải chương trình `main` độc lập. `\u00E9` và `\u0301` là Unicode escapes trong Java source. Hãy nhớ kết quả `false` đến từ việc hai `String` chứa dãy ký tự khác nhau, không phải do lỗi encoding.

```text
composed:
U+0063 U+0061 U+0066 U+00E9
   c      a      f      é

decomposed:
U+0063 U+0061 U+0066 U+0065 U+0301
   c      a      f      e     ◌́
```

Một phép so sánh đơn giản, đối chiếu khóa dữ liệu hoặc tìm kiếm chính xác có thể coi chúng là hai giá trị khác nhau, dù người dùng kỳ vọng giống nhau.

**Unicode normalization** đưa một chuỗi về một trong các **normal forms** được định nghĩa trong *Unicode Standard Annex #15 (UAX #15)*. Khi hai dãy là **canonical equivalents** và được normalize về **cùng một form**, chúng có dạng chuẩn hóa giống nhau.

```text
"caf\u00E9" ─────┐
                 ├── Normalizer.normalize(..., NFC) ──> "caf\u00E9"
"cafe\u0301" ────┘
```

Điều này giúp so sánh theo một quy tắc đã chọn, nhưng không biến mọi ký tự nhìn tương tự thành giống nhau.

## 2. Hai phương thức trọng tâm của `java.text.Normalizer`

API hiện hành:

```java
public static boolean isNormalized(
        CharSequence src, Normalizer.Form form);

public static String normalize(
        CharSequence src, Normalizer.Form form);
```

Đây là **chữ ký rút gọn để học API**, không phải code cần tự khai báo. `Normalizer` thuộc package `java.text`, nằm trong module `java.base` nên ứng dụng Java thông thường không cần thêm dependency bên ngoài.

| Phương thức | Câu hỏi / hành động | Kết quả |
| --- | --- | --- |
| `isNormalized(src, form)` | Chuỗi **đã ở normal form này** chưa? | `true` hoặc `false` |
| `normalize(src, form)` | Tạo chuỗi theo **normal form được chọn**. | `String` đã chuẩn hóa |

Ví dụ trực tiếp:

```java
import java.text.Normalizer;

String input = "cafe\u0301";

boolean alreadyNfc =
        Normalizer.isNormalized(input, Normalizer.Form.NFC); // false

String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);

boolean nowNfc =
        Normalizer.isNormalized(normalized, Normalizer.Form.NFC); // true
```

Đây là **đoạn mã đặt trong method**, cần bối cảnh code Java hợp lệ; xem chương trình độc lập ở mục 6 để chạy từ đầu đến cuối.

### Hợp đồng đầu vào

Cả hai phương thức nhận `CharSequence`, vì vậy có thể truyền `String`, `StringBuilder` hoặc implementation thích hợp khác; `normalize(...)` trả một `String`. Tham số `form` phải là một trong bốn giá trị `Normalizer.Form` đã định nghĩa.

Theo Javadoc Java SE 26:

- `src == null` hoặc `form == null` sẽ gây `NullPointerException`.
- `isNormalized` cho biết tình trạng **theo đúng form truyền vào**. Một chuỗi có thể đã NFC nhưng chưa NFD; không tồn tại câu trả lời “đã chuẩn hóa” hoàn toàn độc lập với form.
- `normalize` trả chuỗi theo form yêu cầu. Nó **không thay đổi** `String` gốc; `String` trong Java là bất biến.
- Không được giả định `normalize` luôn cấp phát một object mới hoặc luôn trả đúng object đầu vào. Khi làm nghiệp vụ, hãy so sánh **nội dung** chứ không dùng toán tử `==` để xác minh.

### Cách đọc và chiều của API

```java
Normalizer.isNormalized(value, Form.NFC);
Normalizer.normalize(value, Form.NFC);
```

Cả hai đều nhận **nội dung trước, form sau**. Không có phương thức instance `value.normalize()` trong `java.lang.String`; chuẩn hóa Unicode nằm trong `java.text.Normalizer`.

## 3. Bốn normal forms: NFC, NFD, NFKC, NFKD

`Normalizer.Form` chứa bốn constant:

| Form | Tên | Thuật toán khái quát | Phù hợp khi |
| --- | --- | --- | --- |
| `NFC` | Normalization Form C | **Canonical decomposition**, sắp thứ tự dấu kết hợp, sau đó **canonical composition** khi có thể | Dữ liệu văn bản phổ thông, so sánh canonical, các trường lưu trữ muốn dạng gọn |
| `NFD` | Normalization Form D | **Canonical decomposition** và sắp thứ tự canonical | Phân tích code points hoặc một số bước xử lý dấu/diacritic có chủ đích |
| `NFKC` | Normalization Form KC | **Compatibility decomposition** rồi canonical composition | Một số khóa tìm kiếm hoặc quy tắc nghiệp vụ chủ động muốn gộp ký tự tương thích |
| `NFKD` | Normalization Form KD | **Compatibility decomposition** và canonical ordering | Phân tích/biến đổi có chủ đích cần compatibility decomposition |

C và D tương ứng **composed** và **decomposed**; chữ **K** nhấn mạnh **compatibility**. Vì có thêm compatibility mapping, NFKC/NFKD có thể làm mất những khác biệt ký tự mà NFC/NFD cố ý giữ.

### 3.1. Canonical normalization

Với `e + COMBINING ACUTE` và `é`, Unicode xác định chúng tương đương về mặt canonical. Vì vậy:

```java
String a = "\u00E9";
String b = "e\u0301";

boolean sameNfc =
        Normalizer.normalize(a, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(b, Normalizer.Form.NFC)); // true

boolean sameNfd =
        Normalizer.normalize(a, Normalizer.Form.NFD)
        .equals(Normalizer.normalize(b, Normalizer.Form.NFD)); // true
```

Các biến `sameNfc` và `sameNfd` đều `true`. Hai phép so sánh dùng **cùng form ở hai phía**.

NFC thường tạo `U+00E9` khi có ký tự dựng sẵn phù hợp; NFD tạo `U+0065 U+0301`. Không phải mọi tổ hợp base + combining mark đều có một mã điểm dựng sẵn: chữ C không có nghĩa “mỗi tổ hợp phải trở thành đúng một code point”.

### 3.2. Compatibility normalization

Ký tự ligature **ﬃ** (`U+FB03` LATIN SMALL LIGATURE FFI) có compatibility decomposition thành ba chữ `f`, `f`, `i`.

```java
String ligature = "\uFB03";

boolean equalWithNFC =
        Normalizer.normalize(ligature, Normalizer.Form.NFC)
                .equals("ffi"); // false

boolean equalWithNFKC =
        Normalizer.normalize(ligature, Normalizer.Form.NFKC)
                .equals("ffi"); // true
```

NFC **giữ** khác biệt giữa ligature `ﬃ` và ba ký tự `ffi`; NFKC **gộp** chúng thành cùng dạng chuẩn tương thích. NFKD cũng cho `ffi` trong ví dụ này.

Các dạng compatibility có thể thay đổi những distinctions liên quan trình bày hoặc ý nghĩa trong một số bối cảnh. **Không áp dụng NFKC/NFKD lên mọi dữ liệu theo phản xạ**. Đặc biệt cân nhắc với văn bản pháp lý, mã sản phẩm, định danh theo giao thức, dữ liệu cần bảo toàn nguyên trạng hoặc nội dung người dùng muốn lưu chính xác.

### 3.3. Bảng code points dễ nhớ

| Chuỗi đầu vào | NFC | NFD | NFKC | NFKD |
| --- | --- | --- | --- | --- |
| `"\u00E9"` (é dựng sẵn) | `U+00E9` | `U+0065 U+0301` | `U+00E9` | `U+0065 U+0301` |
| `"e\u0301"` (e + dấu sắc) | `U+00E9` | `U+0065 U+0301` | `U+00E9` | `U+0065 U+0301` |
| `"\uFB03"` (ligature ﬃ) | `U+FB03` | `U+FB03` | `U+0066 U+0066 U+0069` | `U+0066 U+0066 U+0069` |

Các giá trị ở bảng dùng code points để tránh phụ thuộc cách font/terminal hiển thị. Đối với một dãy nhiều combining marks, quá trình normalization còn có bước **canonical ordering**; đừng định nghĩa NFD đơn giản là “tách một dấu” rồi dừng.

## 4. Khi nào dùng `isNormalized`, khi nào gọi `normalize`?

Cách trực tiếp, dễ đọc nhất:

```java
String canonical = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Không nhất thiết gọi `isNormalized` trước. Nếu mục đích là luôn tạo giá trị chuẩn hóa, gọi `normalize` một lần là đủ.

Nếu bạn có lý do tránh chạy chuyển đổi trên các giá trị đã ở đúng form, có thể:

```java
static String nfcIfNeeded(String input) {
    return Normalizer.isNormalized(input, Normalizer.Form.NFC)
            ? input
            : Normalizer.normalize(input, Normalizer.Form.NFC);
}
```

Đây là một **helper method**, không phải chương trình riêng. Nó dùng `isNormalized` như một nhánh có điều kiện; với `String` bất biến, việc trả `input` khi đã NFC là hợp lý.

**Không mặc định kiểm tra trước luôn nhanh hơn.** `isNormalized` cũng phải xem xét nội dung. Nếu phần lớn input vốn cần chuyển đổi, bạn có thể trả chi phí kiểm tra rồi lại trả chi phí normalize. Cần đo trong workload thực tế mới kết luận chọn nhánh nào tối ưu. Đừng dùng `isNormalized` chỉ vì tên phương thức gợi cảm giác tiết kiệm.

Một cách phân chia theo use case:

- **Cần kiểm tra hợp lệ theo contract:** nếu API chỉ nhận NFC, gọi `isNormalized(..., NFC)` để xác định input có đáp ứng hay không; sau đó **reject hoặc normalize** theo policy đã công bố.
- **Cần canonicalize trước lưu/so sánh:** gọi `normalize(..., NFC)` nhất quán trên mọi đầu vào.
- **Cần canonical decomposition cho bước phân tích tiếp theo:** dùng `normalize(..., NFD)`, nhưng hiểu nó có thể làm tăng số code points.
- **Cần compatibility folding theo nghiệp vụ đã thiết kế:** cân nhắc NFKC/NFKD, thông báo rõ dữ liệu nào có thể bị gộp.

## 5. Quan hệ với `String.equals`, code points và UTF-16

Java `String` là chuỗi các `char` (UTF-16 code units), không phải “một mảng ký tự người dùng nhìn thấy”. Những khái niệm thường bị đánh đồng:

| Khái niệm | Mục đích |
| --- | --- |
| **UTF-16 code unit** | Một `char` của Java; `String.length()` tính số code units. |
| **Unicode code point** | Một giá trị Unicode, có thể chiếm một hoặc hai UTF-16 code units. |
| **Grapheme cluster** | Một cụm ký tự mà người dùng có thể cảm nhận như một đơn vị hiển thị, có thể gồm nhiều code points. |
| **Normalization form** | Quy tắc biến đổi chuỗi code points theo canonical/compatibility equivalence. |

Với `e + COMBINING ACUTE`, chúng ta có **hai code points** nhưng có thể thấy **một grapheme**. Normalize NFC thường chuyển thành `é` dựng sẵn, còn NFD giữ dạng tách. Vì vậy độ dài `String.length()` **có thể thay đổi** khi normalization, và không biểu diễn trực tiếp số “chữ người dùng thấy”.

Để quan sát code points một cách có hệ thống trong Java 17+, dùng:

```java
static String codePoints(String s) {
    return s.codePoints()
            .mapToObj(cp -> String.format(
                    Locale.ROOT, "U+%04X", cp))
            .collect(Collectors.joining(" "));
}
```

Đây là helper dùng trong ví dụ hoàn chỉnh phía sau, cần import `java.util.Locale` và `java.util.stream.Collectors`.

**Không dùng `for (char c : s.toCharArray())` để suy luận mọi Unicode code points.** Một code point ngoài Basic Multilingual Plane dùng surrogate pair trong UTF-16. `String.codePoints()` giúp xử lý đúng đơn vị code point; để xử lý grapheme clusters lại cần chiến lược phân đoạn riêng.

## 6. Ví dụ Java 17+ đầy đủ, biên dịch và chạy được

Bài thực hành sau kiểm tra:

1. `String.equals` với hai chuỗi canonical equivalents vẫn có thể `false` khi chưa normalize.
2. `isNormalized` trả đúng cho NFC/NFD.
3. `normalize` đưa về cùng dạng NFC, đồng thời cho code points chính xác.
4. NFKC/NFKD gộp compatibility ligature `U+FB03` thành ba chữ `ffi`, còn NFC không.
5. Chuẩn hóa có tính **idempotent** theo một form.
6. Dữ liệu nguồn không bị sửa.
7. **Nối hai đoạn mà từng đoạn đã NFC** có thể tạo chuỗi **chưa NFC**.

Tạo file **`NormalizationDemo.java`** với toàn bộ mã:

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizationDemo {
    private static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }
        System.out.println(name + "=true");
    }

    private static String nfcIfNeeded(String input) {
        return Normalizer.isNormalized(input, Form.NFC)
                ? input
                : Normalizer.normalize(input, Form.NFC);
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        check("rawDifferent", !composed.equals(decomposed));
        check("decomposedNotNFC", !Normalizer.isNormalized(decomposed, Form.NFC));
        check("composedIsNFC", Normalizer.isNormalized(composed, Form.NFC));

        String canonical = Normalizer.normalize(decomposed, Form.NFC);
        check("equalAfterNFC", canonical.equals(Normalizer.normalize(composed, Form.NFC)));
        System.out.println("NFC.codePoints=" + codePoints(canonical));

        String expanded = Normalizer.normalize(composed, Form.NFD);
        check("decomposedIsNFD", Normalizer.isNormalized(decomposed, Form.NFD));
        check("composedNotNFD", !Normalizer.isNormalized(composed, Form.NFD));
        System.out.println("NFD.codePoints=" + codePoints(expanded));

        String ligature = "\uFB03";
        check("ligatureNFCisNotLetters",
                !Normalizer.normalize(ligature, Form.NFC).equals("ffi"));
        check("ligatureNFKCequalsLetters",
                Normalizer.normalize(ligature, Form.NFKC).equals("ffi"));
        check("ligatureNFKDequalsLetters",
                Normalizer.normalize(ligature, Form.NFKD).equals("ffi"));
        System.out.println("NFKC.codePoints=" +
                codePoints(Normalizer.normalize(ligature, Form.NFKC)));

        check("nfcIdempotent",
                canonical.equals(Normalizer.normalize(canonical, Form.NFC)));
        check("nfcIfNeeded", nfcIfNeeded(decomposed).equals(composed));
        check("sourceUnchanged", decomposed.equals("cafe\u0301"));

        String left = "e";
        String right = "\u0301";
        check("eachPartIsNFC",
                Normalizer.isNormalized(left, Form.NFC)
                && Normalizer.isNormalized(right, Form.NFC));
        check("concatenationNotNFC",
                !Normalizer.isNormalized(left + right, Form.NFC));
        check("renormalizeAfterConcat",
                Normalizer.normalize(left + right, Form.NFC).equals("\u00E9"));
    }
}
```

### Biên dịch và chạy

Từ thư mục chứa file `NormalizationDemo.java`, dùng **JDK 17 trở lên**:

```bash
javac --release 17 NormalizationDemo.java
java NormalizationDemo
```

Không cần thư viện thứ ba hoặc module path. `Normalizer` nằm trong `java.base`, có sẵn trong Java SE.

### Kết quả thực tế đã kiểm chứng

Chương trình được biên dịch và chạy với **OpenJDK 21** bằng `javac --release 17`. Output chính xác:

```text
rawDifferent=true
decomposedNotNFC=true
composedIsNFC=true
equalAfterNFC=true
NFC.codePoints=U+0063 U+0061 U+0066 U+00E9
decomposedIsNFD=true
composedNotNFD=true
NFD.codePoints=U+0063 U+0061 U+0066 U+0065 U+0301
ligatureNFCisNotLetters=true
ligatureNFKCequalsLetters=true
ligatureNFKDequalsLetters=true
NFKC.codePoints=U+0066 U+0066 U+0069
nfcIdempotent=true
nfcIfNeeded=true
sourceUnchanged=true
eachPartIsNFC=true
concatenationNotNFC=true
renormalizeAfterConcat=true
```

Mỗi dòng `...=true` trong code chỉ được in khi điều kiện tương ứng đúng; nếu sai, helper `check` ném `AssertionError`. Vì vậy chương trình vừa là minh họa vừa là bộ kiểm tra chạy được, không chỉ in một tập các kết quả kỳ vọng viết tay.

**Tại sao in code points thay vì ký tự trực tiếp?** Vì dấu kết hợp và font/terminal có thể khiến hai dãy nhìn giống nhau hoặc bị hiển thị khác nhau. Chuỗi `U+...` giúp xác nhận đúng chuyển đổi Unicode mà không dựa vào cách hiển thị.

## 7. Giải thích từng nhóm phép thử

### 7.1. Hai dạng canonical ban đầu khác nhau

`composed.equals(decomposed)` là `false` vì chuỗi thứ nhất chứa `U+00E9` còn chuỗi thứ hai chứa `U+0065 U+0301` ở cuối. `String.equals` không tự làm normalization.

`isNormalized(decomposed, NFC)` là `false`; `isNormalized(composed, NFC)` là `true`. Khi ta dùng `normalize(..., NFC)` trên cả hai, chúng có thể so sánh bằng `equals` và kết quả `true`.

### 7.2. NFD mở rộng ký tự dựng sẵn

Chuỗi `"caf\u00E9"` khi NFD sẽ chứa code points `U+0063 U+0061 U+0066 U+0065 U+0301`. Trong ví dụ này số code points tăng từ bốn lên năm; đây **không phải** phép xóa dấu, vì `U+0301` vẫn tồn tại.

### 7.3. Ligature và compatibility forms

`NFC` của `U+FB03` vẫn khác ba ký tự `ffi`; `NFKC`/`NFKD` có thể thay bằng `U+0066 U+0066 U+0069`. Đây là **compatibility equivalence**, rộng hơn canonical equivalence.

Điều này giúp ích trong một số trường hợp tìm kiếm, nhưng có thể không phù hợp nếu khác biệt giữa một ký tự đặc biệt và chuỗi chữ thường cần được bảo toàn.

### 7.4. Idempotence

Sau khi `canonical` đã NFC:

```java
Normalizer.normalize(canonical, Form.NFC).equals(canonical) // true
```

Tính chất này gọi là **idempotence**: chuẩn hóa lặp lại **cùng form** không tiếp tục thay đổi nội dung. Đây là bất biến quan trọng cho pipeline ingest hoặc chuẩn hóa dữ liệu trước khi lưu. Không nên mở rộng kết luận thành “mọi chuỗi chuẩn hóa theo **hai form khác nhau theo thứ tự tùy ý** đều giữ nguyên”.

### 7.5. Chuỗi gốc không bị sửa

`String` trong Java bất biến. `Normalizer.normalize(...)` trả kết quả mới về mặt nội dung logic, không viết đè vào `decomposed`. Nếu muốn lưu giá trị chuẩn hóa:

```java
String normalized = Normalizer.normalize(original, Form.NFC);
```

Đừng chỉ gọi `Normalizer.normalize(original, Form.NFC);` rồi bỏ kết quả và tưởng `original` đã được cập nhật.

### 7.6. Nối hai chuỗi NFC có thể làm mất tính NFC

Đây là bẫy khó thấy:

```java
String left = "e";
String right = "\u0301";

boolean eachAlreadyNfc =
        Normalizer.isNormalized(left, Form.NFC)
        && Normalizer.isNormalized(right, Form.NFC); // true

String combined = left + right;
boolean combinedAlreadyNfc =
        Normalizer.isNormalized(combined, Form.NFC); // false

String fixed = Normalizer.normalize(combined, Form.NFC);
```

Hai phần độc lập đã NFC, nhưng khi ghép `e` và dấu sắc, chuỗi mới tạo nên một cặp có thể compose thành `é`. **Tập các chuỗi NFC không đóng dưới phép nối tùy ý.**

Do đó, khi xây một giá trị bằng nhiều mảnh từ người dùng, **chuẩn hóa lại kết quả cuối** tại ranh giới dữ liệu. Tương tự, không tùy tiện chia một chuỗi thành các khúc, normalize từng khúc rồi nối lại mà giả định chắc chắn được toàn chuỗi chuẩn.

## 8. Unicode normalization trong dữ liệu tiếng Việt

Tiếng Việt dùng nhiều dấu thanh và dấu phụ. Một ký tự có thể có dạng dựng sẵn hoặc một chuỗi base letter + combining marks; có trường hợp cần **nhiều combining marks**. Unicode normalization có thể sắp thứ tự dấu kết hợp và compose thành những code points thích hợp khi có mapping canonical.

Ví dụ ý tưởng:

```java
String decomposed = "a\u0306\u0301"; // a + dấu breve + dấu sắc
String canonical = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
```

Đoạn trên là **minh họa**; nếu cần xác nhận code points cụ thể cho dữ liệu sản phẩm, dùng `codePoints(...)` như ví dụ chính thay vì dựa vào mắt nhìn. Với hệ thống tiếp nhận văn bản từ nhiều bộ gõ, thiết bị hoặc bản copy/paste khác nhau, việc chuẩn hóa cùng một form giúp giảm tình trạng các chuỗi canonical equivalent bị coi là khác nhau.

Tuy nhiên:

- **NFC không xóa dấu thanh.** `á` không tự trở thành `a`; nó vẫn là chữ có dấu ở dạng NFC.
- **NFD không tự bỏ dấu.** Nó có thể chuyển dấu thành combining marks nhưng các marks vẫn còn.
- **NFKC không có nghĩa chuyển mọi chữ tiếng Việt sang ASCII.** Một số chữ cái như `đ` không phải phiên bản canonical/compatibility của `d`.
- Chuẩn hóa Unicode **không tự điều chỉnh chính tả**, không nhận diện từ tiếng Việt và không sửa lỗi bộ gõ.
- Trong một số ngữ cảnh, dấu tiếng Việt có ý nghĩa phân biệt từ và danh tính; bỏ dấu có thể gây va chạm hoặc làm sai dữ liệu.

Nếu nghiệp vụ cần **tìm kiếm không phân biệt dấu**, phải xây một chiến lược tìm kiếm riêng. Có thể có bước NFD rồi xử lý combining marks, nhưng đây là phép **biến đổi mất thông tin** và không tương đương normalizing. Không thay thế dữ liệu gốc bằng bản đã bỏ dấu chỉ vì muốn hỗ trợ search.

## 9. Normalization không phải case folding, collation hay chống giả mạo Unicode

Những vấn đề này liên quan Unicode nhưng có câu hỏi khác nhau:

| Nhu cầu | Normalizer có giải quyết đầy đủ không? | Cần cân nhắc |
| --- | --- | --- |
| Hai dãy canonical equivalents | **Có**, khi normalize về cùng form. | NFC/NFD nhất quán |
| Hai compatibility equivalents | Chỉ với **NFKC/NFKD**, tùy mapping. | Rủi ro gộp khác biệt |
| `"A"` và `"a"` | **Không**. | Case mapping/case folding, locale và quy tắc nghiệp vụ |
| Sắp xếp theo ngôn ngữ | **Không**. | `Collator` và cấu hình locale/strength phù hợp |
| Tìm kiếm không phân biệt dấu | **Không tự động**. | Index/search analysis có quy tắc rõ |
| Ký tự Latin `a` với ký tự từ bảng chữ khác nhìn giống `a` | **Không bảo đảm**. | Unicode confusables/spoofing protection độc lập |
| Grapheme cluster, emoji sequence | **Không phải** thuật toán phân đoạn hiển thị. | Grapheme breaking và UI handling |
| Kiểm tra chuỗi hợp lệ với identifier/password | **Không đầy đủ**. | Validation/schema, bảo mật, policy chuẩn hóa riêng |

Ví dụ, `Normalizer.normalize("ABC", Form.NFC)` không tự đổi thành `"abc"`. Tương tự, NFKC không phải bộ lọc chống mọi ký tự giả mạo. Các chữ trông giống nhau từ những script khác nhau có thể vẫn là code points khác nhau sau mọi form normalization.

**Với định danh bảo mật:** chuẩn hóa là một phần của thiết kế giao thức, không phải một nút “bảo mật hơn”. Các hệ thống có thể đặt quy tắc khác nhau về NFKC, case mapping, ký tự được phép và cảnh báo confusables. Chỉ normalize theo form mà giao thức/ứng dụng đã định nghĩa và kiểm thử; đừng tự gộp các tài khoản hoặc thay đổi ý nghĩa secret sau khi hệ thống đã vận hành.

## 10. Thiết kế pipeline lưu trữ và so sánh nhất quán

Một luồng dữ liệu văn bản thường có các bước:

```text
Bytes từ client/file/network
         |
         v
Decode charset (ví dụ UTF-8)
         |
         v
Kiểm tra policy input và xử lý null/size
         |
         v
Normalizer.normalize(text, Form.NFC)
         |
         +--> lưu giá trị canonical (nếu contract cho phép)
         |
         +--> dùng khóa so sánh/tìm kiếm cùng policy
```

**Thứ tự cần được thiết kế cẩn thận.** Nếu giới hạn độ dài dùng số code points hoặc số UTF-16 units, normalization có thể thay đổi kết quả đếm. Bởi vậy, nếu ứng dụng giới hạn kích thước đầu vào cho hiệu năng, cần kiểm tra kích thước thô trước; nếu giới hạn tính hợp lệ của **giá trị được lưu**, cũng nên kiểm tra sau khi normalize.

### 10.1. Chọn một form rõ ràng

Đối với văn bản chung mà canonical equivalence là nhu cầu, **NFC thường là mặc định phù hợp**. Khi hệ thống có quy chuẩn định danh, tìm kiếm hoặc compatibility riêng, hãy mô tả cụ thể vì sao dùng NFKC hoặc form khác.

Đừng có một nơi lưu NFC nhưng phía tra cứu dùng NFD mà đem so sánh bằng `String.equals`. Tất cả nơi phát hành/kiểm tra cùng một khóa phải tuân theo **cùng chính sách**.

### 10.2. So sánh sau khi normalize hai phía

```java
static boolean canonicallyEqual(String left, String right) {
    return Normalizer.normalize(left, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(right, Normalizer.Form.NFC));
}
```

Đây là **helper minh họa**, giả định `left` và `right` không null. Nó kiểm tra equality **sau canonical normalization NFC**. Không đồng nghĩa equality không phân biệt hoa/thường, dấu, locale hoặc compatibility forms.

Với dữ liệu lớn, nên quyết định lưu canonical key và cache ở tầng phù hợp thay vì normalize lặp lại trong mọi phép so sánh; đồng thời phải bảo đảm **key thực tế được tạo và tra theo cùng pipeline**.

### 10.3. Lưu bản gốc hay bản chuẩn hóa?

Tùy yêu cầu. Nếu cần bảo toàn nguyên văn input (audit, tài liệu, chữ ký dữ liệu, bản gốc người dùng nhập), có thể lưu **raw text** riêng và tạo thêm **normalized comparison key**. Nếu contract đã quy định canonicalization trước khi ghi, có thể chỉ lưu giá trị chuẩn hóa, nhưng phải ghi rõ với đối tác/clients.

**Không sửa dữ liệu đã ký hoặc băm rồi mong chữ ký/hash vẫn khớp.** Normalize làm đổi dãy code units/bytes đối với những input cần chuyển đổi; nếu hệ thống ký/băm bytes, cần chuẩn hóa theo protocol **trước** bước đó hoặc tuyệt đối không sửa dữ liệu sau khi ký.

### 10.4. Database index và migration

Nếu ứng dụng có khóa uniqueness theo form chuẩn hóa, áp dụng cùng một hàm ở cả đường ghi, đường kiểm tra uniqueness và truy vấn. Khi chuyển dữ liệu cũ sang NFC/NFKC, có thể xuất hiện **va chạm** do những chuỗi trước đó khác nhau nay trở thành cùng key. Hãy lập báo cáo collision và giải quyết theo nghiệp vụ trước khi bật ràng buộc unique; không tự ghi đè bản ghi.

Không giả định database collation, Java Normalizer và bộ phân tích tìm kiếm luôn cho kết quả tương đương. Những engine đó có thể có quy tắc riêng về locale, case và accent.

## 11. Lưu ý về Unicode version và hệ điều hành

Unicode Standard có những phiên bản mới. JDK khác nhau có thể tích hợp dữ liệu Unicode ở các mức khác nhau; Java SE 26 tài liệu hóa dữ liệu Unicode mới hơn so với các JDK cũ. Khi kiểm thử chuỗi đặc biệt hoặc những ký tự mới được thêm gần đây, cần biết **JDK/Unicode version** của môi trường.

Nhưng **đừng viết logic phụ thuộc vào giả định “chạy JDK mới sẽ tự đổi mọi chuỗi NFC đã ổn định trước đây”**. Unicode normalization có các chính sách ổn định lâu dài. Với một hệ thống cần byte-for-byte deterministic key giữa các dịch vụ, vẫn nên kiểm thử thống nhất trên những runtime mà hệ thống thực tế sử dụng và ghi rõ chính sách normalization.

Không cần chọn thuật toán khác nhau theo Windows/Linux/macOS chỉ vì Unicode: `java.text.Normalizer` là API Java chuẩn. Tuy nhiên bước nhập/giải mã bytes, font hiển thị, cách nhập từ bàn phím, collation của database và các thư viện khác có thể khác nhau; đừng nhầm những khác biệt đó với bản thân normalization.

## 12. Các edge cases cần kiểm thử

### 12.1. Empty string

Chuỗi rỗng đã được chuẩn hóa theo mọi normal form; normalize chuỗi rỗng vẫn là chuỗi rỗng.

```java
boolean ok = Normalizer.isNormalized("", Normalizer.Form.NFC); // true
String result = Normalizer.normalize("", Normalizer.Form.NFC);  // ""
```

Đây là đoạn minh họa. Đối với ứng dụng, nếu không cho phép tên rỗng thì đó là validation của schema, không phải vấn đề Unicode normalization.

### 12.2. Null input

```java
// Normalizer.normalize(null, Normalizer.Form.NFC);
// => NullPointerException theo Javadoc.
```

Tương tự, truyền `null` cho `form` không hợp lệ. Nếu API nội bộ được thiết kế cho đầu vào nullable, hãy xử lý null rõ ràng trước khi gọi Normalizer; không giả định `null` là một chuỗi rỗng.

### 12.3. Dữ liệu `CharSequence` có thể thay đổi

`StringBuilder` cũng là `CharSequence`. Nếu một luồng đang sửa nội dung trong khi luồng khác gọi normalization, kết quả có thể không được kiểm soát như một snapshot ổn định. Trong hệ thống đa luồng, cố định input thành một `String` không thay đổi trước khi xử lý.

### 12.4. Chuỗi malformed UTF-16

Java `String` có thể chứa unpaired surrogate theo các thao tác tạo chuỗi bất thường. `Normalizer` có chức năng normalizing text, **không phải API validate toàn bộ quy tắc UTF-16, UTF-8 hoặc Unicode security profile**. Nếu dữ liệu cần hợp lệ theo một chuẩn encoding nghiêm ngặt, hãy validate ở bước nhập và decode thay vì trông chờ `isNormalized` phát hiện mọi vấn đề.

### 12.5. Dấu kết hợp ở ranh giới nối

`isNormalized(partA, NFC) && isNormalized(partB, NFC)` **không bảo đảm** `isNormalized(partA + partB, NFC)`. Demo chứng minh điều đó bằng `"e" + "\u0301"`. Normalize toàn bộ chuỗi sau thao tác nối hoặc dùng thuật toán streaming normalization có xử lý ranh giới chuẩn.

### 12.6. Chuỗi dài và hiệu năng

Với input lớn, normalization cần xử lý chuỗi code points và có thể tạo nội dung có chiều dài khác. Cần giới hạn độ dài và cấp phát theo yêu cầu hệ thống. Không chọn giữa “check rồi normalize” và “normalize trực tiếp” bằng trực giác tốc độ; hãy benchmark với phân bố input thật.

### 12.7. Normal form và nghiệp vụ

Một chuỗi có thể đã ở NFC nhưng chưa NFD (và ngược lại). `isNormalized` không chứng minh chuỗi hợp lệ để sử dụng làm username, email, domain name hoặc path. Mỗi loại định danh có **quy chuẩn riêng**; Unicode normalization chỉ là một thành phần khi quy chuẩn đó cho phép.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai chuỗi nhìn giống nhau nhưng `equals` trả `false` | Dạng composed và decomposed khác nhau. | Normalize **cả hai** về cùng một form, thường là NFC khi phù hợp. |
| Gọi `normalize(...)` rồi thấy biến gốc không đổi | `String` bất biến; bỏ qua giá trị trả về. | Gán kết quả vào biến mới hoặc thay reference có chủ đích. |
| `isNormalized(text, NFD) == false` dù text đã NFC | Đang kiểm tra **form khác**. | Xác định chính sách form và kiểm tra đúng form đó. |
| NFKC làm hai khóa trước đây khác nhau trở thành giống nhau | Compatibility mappings rộng hơn canonical. | Chọn lại policy, xử lý collision và dữ liệu nguồn. |
| Đã normalize từng phần nhưng chuỗi nối chưa NFC | Normalization không đóng dưới phép nối tùy ý. | Normalize giá trị hoàn chỉnh sau khi ghép. |
| Mong NFD tạo chuỗi bỏ dấu | NFD vẫn giữ combining marks. | Thiết kế pipeline tìm kiếm không phân biệt dấu riêng, không gọi đó là normalization. |
| Mong NFC hoặc NFKC tự lowercase | Normalization không phải case folding. | Tách rõ case handling và locale-sensitive behavior. |
| Tưởng normalize giải quyết spoofing/confusables | Nhiều code points trông giống nhau không canonical/compatibility equivalent. | Bổ sung security profile/identifier validation thích hợp. |
| Dùng `s.length()` làm số ký tự hiển thị | Java đo UTF-16 code units, không phải grapheme clusters. | Dùng đúng phép đếm theo requirement; `codePoints()` chỉ giải quyết code points. |
| `NullPointerException` khi normalize | `src` hoặc `form` bằng null. | Validate null và chọn form tường minh. |
| Normalize tại tầng ghi nhưng không tầng đọc | Không nhất quán policy. | Chuẩn hóa cả query/key và dữ liệu hoặc lưu canonical key. |
| So sánh Unicode bằng `==` | `==` so object identity, không so giá trị nội dung. | Dùng `String.equals` trên hai chuỗi đã chuẩn hóa cùng form. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `"caf\u00E9"` và `"cafe\u0301"` hiển thị giống nhau. Tại sao `equals` lại `false`?

**Đáp:** Hai chuỗi có code point sequences khác nhau (`U+00E9` so với `U+0065 U+0301`). `String.equals` không tự chuẩn hóa.

**Câu 2.** Cần kiểm tra một chuỗi đã ở NFC chưa, gọi gì?

**Đáp:** `Normalizer.isNormalized(text, Normalizer.Form.NFC)`. Hàm trả boolean; nó không tự biến đổi giá trị.

**Câu 3.** Muốn chuyển sang NFC, gọi gì? Chuỗi gốc có thay đổi không?

**Đáp:** `String result = Normalizer.normalize(text, Normalizer.Form.NFC)`. `String` gốc không bị sửa, phải dùng giá trị trả về.

**Câu 4.** NFD của `é` dựng sẵn có tự bỏ dấu sắc không?

**Đáp:** Không. Nó chuyển sang `e + COMBINING ACUTE`, dấu vẫn tồn tại.

**Câu 5.** Vì sao NFKC có thể biến `ﬃ` thành `ffi` nhưng NFC không?

**Đáp:** NFKC cho phép **compatibility decomposition**, còn NFC xử lý **canonical equivalence** và giữ khác biệt compatibility này.

**Câu 6.** Hai chuỗi đều có `isNormalized(..., NFC) == true`. Nối lại có chắc vẫn NFC không?

**Đáp:** Không. `"e"` và `"\u0301"` đều NFC riêng lẻ nhưng kết quả nối có thể compose thành `é`, nên chuỗi ghép chưa NFC. Chuẩn hóa lại sau khi nối.

**Câu 7.** `normalize(text, NFKC)` có thể dùng trực tiếp làm giải pháp chống Unicode spoofing và chuẩn hóa mật khẩu không?

**Đáp:** Không. Nó không thay thế policy định danh/credentials và không bao quát confusables. Dữ liệu nhạy cảm phải theo chuẩn của giao thức, bảo toàn những khác biệt cần thiết và kiểm tra rủi ro collision.

**Câu 8.** Tại sao không luôn gọi `isNormalized` trước `normalize` để tăng tốc?

**Đáp:** `isNormalized` cũng có chi phí kiểm tra. Nếu hầu hết dữ liệu cần đổi dạng, ta có thể tốn hai lần làm việc. Chọn theo phép đo và mục đích (validate hay transform).

**Câu 9.** Chuyển sang NFC có giúp `String.length()` phản ánh số grapheme clusters không?

**Đáp:** Không. NFC có thể giảm code points/UTF-16 units trong vài trường hợp, nhưng grapheme segmentation là một vấn đề khác.

**Câu 10.** Khi hệ thống dùng normalized key để tra dữ liệu, cần thống nhất điều gì?

**Đáp:** Form normalization, cách xử lý case/compatibility nếu có, version/policy cho những dữ liệu đặc biệt, ranh giới normalize và quy tắc xử lý collision. Cả đường ghi và đường tra cứu phải áp dụng nhất quán.

## 15. Bài tập thực hành đề xuất

### Bài 1 — Chuẩn hóa trước khi tìm kiếm chính xác

Tạo hai `String` từ cùng một chữ có dấu, một dạng dựng sẵn và một dạng combining. Kiểm tra:

1. `equals` ban đầu trả `false`.
2. Hai chuỗi sau `Normalizer.normalize(..., NFC)` có `equals == true`.
3. `isNormalized(..., NFC)` trả `true` cho hai kết quả mới.

Không thêm bước lowercase hay xóa dấu vì yêu cầu chỉ là **canonical equivalence**.

### Bài 2 — Xác minh tính idempotent

Lấy 4–5 chuỗi gồm ASCII, tiếng Việt, dấu kết hợp, ligature và emoji. Với mỗi form `F`, kiểm tra:

```java
String once = Normalizer.normalize(text, F);
String twice = Normalizer.normalize(once, F);

if (!once.equals(twice)) {
    throw new AssertionError("Normalization must be idempotent");
}
```

Đây là **đoạn trong vòng lặp test** với `text`, `F` được định nghĩa trước; không phải file độc lập. Đừng mặc định đầu ra NFC và NFKC của mọi test string luôn bằng nhau.

### Bài 3 — Kiểm tra ranh giới nối

Tạo `left = "e"`, `right = "\u0301"`. Chứng minh hai phần riêng đã NFC nhưng `left + right` chưa NFC. Sau đó chuẩn hóa chuỗi ghép và in code points.

### Bài 4 — Đánh giá policy tìm kiếm

Cho dữ liệu hiển thị nguyên bản là `ﬃ`, `ffi` và hai cách biểu diễn `é`. Tạo hai key:

- `canonicalKey = normalize(text, NFC)`;
- `compatibilityKey = normalize(text, NFKC)`.

Xác định những nhóm dữ liệu sẽ bị gộp trong mỗi key, rồi thảo luận khi nào được phép đưa key vào unique index. Không thay đổi dữ liệu gốc nếu người dùng cần bảo toàn chính xác.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized`, `Normalizer.Form`, hợp đồng đầu vào/null và ví dụ ký tự dựng sẵn/chuỗi tách.
- [Oracle Java SE 26 — `Normalizer.Form`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.Form.html): `NFC`, `NFD`, `NFKC`, `NFKD`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): canonical/compatibility decomposition, composition, ordering, tính ổn định và những quy tắc thiết yếu của normalization.
- [Oracle Java SE 26 — `String`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): UTF-16, `equals`, `codePoints`, `length`.
- [Oracle Java SE 26 — `Character`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html): code points, surrogate pairs và phiên bản dữ liệu Unicode được Java hỗ trợ.

**Ghi nhớ:** `isNormalized(text, form)` **kiểm tra** văn bản đã theo một normal form hay chưa; `normalize(text, form)` **chuyển** văn bản về dạng đó và trả một `String`. NFC/NFD giải quyết canonical equivalence, NFKC/NFKD mở rộng sang compatibility mappings. Luôn thống nhất form theo quy tắc sản phẩm, chuẩn hóa lại sau khi nối các mảnh có thể tương tác, và đừng nhầm Unicode normalization với xóa dấu, lowercase, collation hoặc Unicode security.
