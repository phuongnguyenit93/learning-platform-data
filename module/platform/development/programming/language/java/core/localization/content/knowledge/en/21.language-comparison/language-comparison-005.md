# Chế độ phân rã của Collator và quan hệ với chuẩn hóa Unicode trong Java

## 1. Vì sao hai chuỗi trông giống nhau mà so sánh khác nhau?

Trong một ứng dụng đa ngôn ngữ, hai người dùng có thể nhập chữ `é` theo hai biểu diễn Unicode khác nhau:

- **Dựng sẵn (precomposed):** `U+00E9`, ký tự `é`.
- **Kết hợp (decomposed):** `U+0065` (`e`) + `U+0301` (COMBINING ACUTE ACCENT).

Hai dạng thường được nhìn nhận như cùng một chữ có dấu, nhưng `String.equals` so sánh nội dung `String` theo UTF-16, nên chúng **không bằng nhau**. Tương tự, chữ Latin `Ａ` dạng full-width (`U+FF21`) và `A` (`U+0041`) có hình thức liên quan nhưng **khác code point**.

Nếu sắp xếp hoặc tìm kiếm tên người theo tiếng Việt, tiếng Pháp, tiếng Đức và nhiều ngôn ngữ khác, chỉ so sánh code units theo thứ tự nhị phân là chưa đủ. Java cung cấp `java.text.Collator` để **so sánh chuỗi theo quy tắc ngôn ngữ (collation)** và `java.text.Normalizer` để **chuẩn hóa dãy ký tự Unicode**. Một phần quan trọng của `Collator` là chế độ **decomposition** — phân rã trước/trong quá trình xử lý collation.

Bài này phân biệt ba chế độ `NO_DECOMPOSITION`, `CANONICAL_DECOMPOSITION`, `FULL_DECOMPOSITION`; mối quan hệ của chúng với `Normalizer.Form.NFD`/`NFKD`; sự độc lập giữa **decomposition** và **strength**; ví dụ Java 17+ có thể chạy; cùng những cảnh báo về so sánh, tìm kiếm, khóa dữ liệu và hiệu năng.

## 2. Collator làm gì và không làm gì?

`Collator` là một `Comparator<Object>` chuyên cho văn bản theo `Locale`. Tạo bằng factory:

```java
import java.text.Collator;
import java.util.Locale;

Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
int comparison = vietnamese.compare("an", "bình");
```

Đây là **snippet** đặt trong một phương thức. Kết quả `compare` âm/0/dương cho biết thứ tự collation, **không phải** thứ tự code point hay thứ tự byte UTF-8. Kết quả chi tiết phụ thuộc quy tắc locale/provider của Java runtime.

Các API chính:

| API | Ý nghĩa |
| --- | --- |
| `Collator.getInstance(locale)` | Lấy bộ so sánh cho locale |
| `compare(a, b)` | Trả số âm, 0 hoặc số dương theo collation |
| `setStrength(level)` | Chọn **mức độ khác biệt** được xét |
| `getStrength()` | Đọc mức độ khác biệt hiện tại |
| `setDecomposition(mode)` | Chọn **cách phân rã Unicode** trong collation |
| `getDecomposition()` | Đọc chế độ phân rã hiện tại |
| `getCollationKey(text)` | Tạo khóa so sánh/sắp xếp cho cùng cấu hình collator |
| `clone()` | Tạo bản sao để cấu hình hoặc sử dụng riêng |

**Collation không phải normalization.** `Collator.compare(a, b) == 0` chỉ có nghĩa hai chuỗi được coi tương đương **dưới cấu hình so sánh hiện tại**, không có nghĩa `a.equals(b)`, `a.getBytes(...)` hay định danh nghiệp vụ của chúng bằng nhau. Một collator ở mức `PRIMARY` có thể xem hai chuỗi có dấu khác nhau là tương đương, nhưng điều đó chưa chứng minh chúng có quan hệ chuẩn hóa Unicode.

## 3. Ba chế độ phân rã của Collator

Java định nghĩa ba hằng số nguyên trong `Collator`:

```java
Collator.NO_DECOMPOSITION
Collator.CANONICAL_DECOMPOSITION
Collator.FULL_DECOMPOSITION
```

Thiết lập trên một instance:

```java
Collator collator = Collator.getInstance(Locale.US);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
int selectedMode = collator.getDecomposition();
```

| Chế độ | Ý nghĩa | Liên hệ Unicode normalization | Khi nào cân nhắc |
| --- | --- | --- | --- |
| `NO_DECOMPOSITION` | Không thực hiện phân rã ký tự đầu vào như bước cấu hình riêng | Không tương ứng với một normalization form bắt buộc | Khi chắc chắn dữ liệu/locale không cần phân rã hoặc đã xử lý đầu vào thích hợp; ưu tiên tốc độ có điều kiện |
| `CANONICAL_DECOMPOSITION` | Phân rã các **biến thể tương đương chuẩn tắc (canonical equivalents)** | Tương ứng dạng phân rã chuẩn tắc `NFD` | So sánh văn bản có dấu, chuỗi có dạng tổ hợp/dựng sẵn |
| `FULL_DECOMPOSITION` | Phân rã cả **canonical** và **compatibility equivalents** | Tương ứng dạng phân rã tương thích `NFKD` | Khi cần xử lý cả biến thể định dạng như full-width/half-width và những ký tự có compatibility decomposition |

Theo tài liệu Java SE, `NO_DECOMPOSITION` có thể nhanh nhất, nhưng không phải luôn cho so sánh đúng với ngôn ngữ có dấu. `CANONICAL_DECOMPOSITION` giúp xử lý chính xác các biến thể dấu, còn `FULL_DECOMPOSITION` xử lý thêm nhiều dạng tương thích với chi phí cao hơn. Chi phí thực tế phụ thuộc dữ liệu, implementation, cache và khối lượng so sánh; **không mặc định FULL luôn cần thiết**.

Một điểm tinh tế: implementation `RuleBasedCollator` có thể **tự sinh các ánh xạ ký tự dựng sẵn** khi biên dịch bảng luật collation. Vì thế ngay cả `NO_DECOMPOSITION` đôi khi vẫn coi dạng dựng sẵn và dạng kết hợp của một chữ là tương đương tại một số mức strength. Không được suy luận ngược rằng chỉ vì `compare` trả 0 nên chế độ phân rã đang bật, hoặc rằng `NO_DECOMPOSITION` **luôn** trả khác 0 cho mọi cặp canonical-equivalent.

### 3.1. NO_DECOMPOSITION

Ở chế độ này, collator không tiến hành phân rã ký tự theo cấu hình của chế độ decomposition. Một điểm cộng là có thể ít công việc hơn; nhược điểm là chuỗi có tổ hợp dấu theo thứ tự khác hoặc các biến thể chưa có trong bảng luật có thể không được xử lý như mong đợi.

```java
collator.setDecomposition(Collator.NO_DECOMPOSITION);
```

Chỉ chọn khi đã xác nhận tính phù hợp với bộ chữ, quy tắc dữ liệu và phiên bản triển khai đang dùng. Nếu đầu vào đa nguồn chứa Unicode với dấu kết hợp, dùng `CANONICAL_DECOMPOSITION` thường dễ bảo đảm hơn.

### 3.2. CANONICAL_DECOMPOSITION

Ở chế độ này, các dạng Unicode tương đương chuẩn tắc được phân rã theo quy tắc liên quan đến `NFD`. Ví dụ:

```text
U+00E9       →  U+0065 U+0301
é (dựng sẵn)    e + dấu sắc kết hợp
```

Có thể thiết lập:

```java
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

Phân rã canonical không tự xóa dấu hoặc bỏ qua phân biệt hoa/thường. **Dấu có được coi là khác biệt khi so sánh hay không** còn phụ thuộc `strength` (và luật locale). Vì vậy `CANONICAL_DECOMPOSITION` **không tương đương** với “so sánh bỏ dấu”.

### 3.3. FULL_DECOMPOSITION

`FULL_DECOMPOSITION` xử lý cả tương đương chuẩn tắc lẫn các dạng tương thích (compatibility):

```text
U+FF21  FULLWIDTH LATIN CAPITAL LETTER A → U+0041 A
U+FB00  LATIN SMALL LIGATURE FF          → U+0066 U+0066 (ff)
```

Có thể thiết lập:

```java
collator.setDecomposition(Collator.FULL_DECOMPOSITION);
```

Trong ví dụ này các ký tự có ý nghĩa liên quan có thể được so sánh theo cơ sở chung. Nhưng phân rã tương thích **có thể đánh mất phân biệt hình thức/ý nghĩa ứng dụng** (ví dụ giữa dạng full-width và ASCII). Không dùng FULL để tuyên bố hai identifier, mật khẩu hoặc mã bảo mật là cùng một giá trị, trừ khi quy chuẩn của hệ thống chỉ rõ.

## 4. Strength và decomposition là hai trục cấu hình riêng

`Collator` còn có bốn mức `strength`:

| Strength | Khác biệt được xem xét (khái quát) | Ví dụ thường gặp |
| --- | --- | --- |
| `PRIMARY` | Khác biệt chữ cơ bản | “a” và “á” có thể xem gần như nhau theo nhiều locale |
| `SECONDARY` | Thêm khác biệt dấu | “a” và “á” thường được phân biệt |
| `TERTIARY` | Thêm khác biệt hoa/thường/biến thể | “a” và “A” thường được phân biệt |
| `IDENTICAL` | Thêm những khác biệt chưa xét ở mức thấp hơn | Có thể phân biệt biểu diễn Unicode khi chưa phân rã tương ứng |

Mô tả trên chỉ là mô hình học; việc phân biệt chữ nào ở cấp nào phụ thuộc **quy tắc locale và provider**. `PRIMARY` không phải một hàm chuẩn “xóa mọi dấu” và `TERTIARY` không có nghĩa “bắt buộc bằng `String.equals`”.

Hai thiết lập **không thay thế nhau**:

- `strength`: **loại khác biệt nào quan trọng** trong so sánh.
- `decomposition`: **các ký tự được phân rã như thế nào** để so sánh.

Ví dụ `"é"` so với `"e"` có thể bằng nhau ở `PRIMARY` dù decomposition bật hoặc tắt, vì dấu bị bỏ qua ở mức strength đó. Ngược lại, `"é"` so với `"e\u0301"` là hai cách mã hóa **cùng chữ có dấu**, nên bật canonical decomposition cho phép so sánh nhất quán hơn ngay cả khi strength tăng lên `IDENTICAL`.

### 4.1. Chọn cấu hình theo nhu cầu

**Tìm kiếm có thể bỏ qua dấu:** bắt đầu bằng `Collator.getInstance(userLocale)` và kiểm tra `PRIMARY` với bộ từ thực tế. Nhưng phải thiết kế riêng quy tắc nào được bỏ qua, không nên dùng nó làm bước kiểm soát danh tính.

**Sắp xếp tên theo dấu và chữ hoa/thường:** `SECONDARY` hoặc `TERTIARY` là các điểm bắt đầu, kết hợp `CANONICAL_DECOMPOSITION` khi đầu vào có nhiều cách biểu diễn dấu.

**Yêu cầu phân biệt cả các biến thể Unicode cực nhỏ:** có thể thử `IDENTICAL`, nhưng vẫn phụ thuộc decomposition. Nếu cần kiểm tra chính xác UTF-16, dùng `String.equals`; nếu cần byte-exact, so sánh bytes theo encoding đã xác định.

## 5. Ví dụ chạy được: NO, CANONICAL và FULL tại strength IDENTICAL

Để thấy chế độ decomposition rõ nhất, cố định `Locale.US` và `strength = IDENTICAL`, rồi so sánh ba cặp:

1. `"\u00E9"` (é dựng sẵn) với `"e\u0301"` (e + dấu sắc): canonical-equivalent.
2. `"\uFF21"` (full-width A) với `"A"`: compatibility-equivalent, không phải canonical-equivalent.
3. `"\uFB00"` (ligature ff) với `"ff"`: compatibility-equivalent, không phải canonical-equivalent.

Tạo file **`CollatorDecompositionDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorDecompositionDemo {
    private static void show(String modeName, int mode,
                             String composed, String decomposed,
                             String wide, String plain,
                             String ligature, String letters) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(mode);

        System.out.println(modeName
                + " | accent=" + (collator.compare(composed, decomposed) == 0)
                + " | width=" + (collator.compare(wide, plain) == 0)
                + " | ligature=" + (collator.compare(ligature, letters) == 0));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String wide = "\uFF21";
        String plain = "A";
        String ligature = "\uFB00";
        String letters = "ff";

        show("NO", Collator.NO_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
        show("CANONICAL", Collator.CANONICAL_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
        show("FULL", Collator.FULL_DECOMPOSITION,
                composed, decomposed, wide, plain, ligature, letters);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 CollatorDecompositionDemo.java
java CollatorDecompositionDemo
```

**Output được kiểm tra trên JDK 24 (Locale.US, provider mặc định tại môi trường thử):**

```text
NO | accent=false | width=false | ligature=false
CANONICAL | accent=true | width=false | ligature=false
FULL | accent=true | width=true | ligature=true
```

Giải thích:

- **NO:** không bật phân rã; ở mức `IDENTICAL` của provider thử nghiệm, các cặp được phân biệt.
- **CANONICAL:** cặp chữ `é` có hai biểu diễn trở nên tương đương về collation. Chữ full-width `Ａ` và ligature `ﬀ` là tương đương **tương thích**, chưa được giải quyết bằng phân rã canonical.
- **FULL:** các cặp có canonical hoặc compatibility decomposition phù hợp đều được coi tương đương trong phép thử này.

**Lưu ý tính di động:** `Collator` là factory có thể được cung cấp bởi các `CollatorProvider`/dữ liệu locale khác nhau. Mẫu output trên là một ca kiểm thử đã quan sát, không phải lời hứa rằng mọi provider/JDK sẽ có đúng cùng bảng collation. Trong test sản phẩm, hãy cố định JDK/provider hoặc test các bất biến mà hợp đồng ứng dụng yêu cầu.

Chương trình dùng `compare(...) == 0` chứ không kiểm tra giá trị số tuyệt đối `-1` hoặc `1`, vì `Comparator` chỉ hứa **âm, 0, dương** chứ không hứa magnitude cụ thể.

## 6. Mối quan hệ với java.text.Normalizer: NFD, NFKD, NFC và NFKC

`java.text.Normalizer` biến đổi **nội dung chuỗi** thành một dạng chuẩn hóa Unicode. Đây là API khác `Collator`:

```java
String normalized = Normalizer.normalize(
        input, Normalizer.Form.NFC);
```

Các form của `Normalizer`:

| Form | Tên | Chức năng |
| --- | --- | --- |
| `NFD` | Canonical Decomposition | Phân rã theo tương đương chuẩn tắc; sắp xếp lại combining marks theo chuẩn |
| `NFC` | Canonical Decomposition, followed by Composition | Phân rã canonical rồi tổ hợp chuẩn tắc khi có thể |
| `NFKD` | Compatibility Decomposition | Phân rã canonical và compatibility |
| `NFKC` | Compatibility Decomposition, followed by Composition | Phân rã compatibility rồi tổ hợp chuẩn tắc khi có thể |

Hai quan hệ ý tưởng thường gặp:

- `Collator.CANONICAL_DECOMPOSITION` ↔ mức phân rã tương ứng **`Normalizer.Form.NFD`**.
- `Collator.FULL_DECOMPOSITION` ↔ mức phân rã tương ứng **`Normalizer.Form.NFKD`**.

Đây **không phải** khẳng định `Collator` gọi phương thức `Normalizer.normalize` rồi trả lại chuỗi đã biến đổi. `Collator` **so sánh** theo luật và mức strength, còn `Normalizer` **tạo ra chuỗi mới** đã chuẩn hóa.

### 6.1. So sánh canonical equivalence bằng Normalizer

```java
String a = "\u00E9";
String b = "e\u0301";

boolean rawEqual = a.equals(b); // false

String normalizedA = Normalizer.normalize(
        a, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(
        b, Normalizer.Form.NFC);

boolean canonicalEqual = normalizedA.equals(normalizedB); // true
```

Cặp này tương đương canonical. Có thể dùng `NFD` thay vì `NFC` nếu quy trình dữ liệu cần dạng tách dấu. Trong phần lớn UI lưu trữ thông thường, `NFC` thường là dạng tiện dụng, nhưng chọn form phải dựa trên hợp đồng dữ liệu.

### 6.2. So sánh compatibility equivalence bằng Normalizer

```java
String wide = "\uFF21";
String ascii = "A";

boolean nfdEqual = Normalizer.normalize(
        wide, Normalizer.Form.NFD).equals(
        Normalizer.normalize(ascii, Normalizer.Form.NFD));  // false

boolean nfkdEqual = Normalizer.normalize(
        wide, Normalizer.Form.NFKD).equals(
        Normalizer.normalize(ascii, Normalizer.Form.NFKD)); // true
```

**NFKD/NFKC có thể làm mất phân biệt có ý nghĩa.** Ví dụ chữ dạng full-width, ký tự ligature hoặc chữ số trên/dưới dòng có thể biến thành dạng tương thích phổ biến. Do đó không thay `NFC` bằng `NFKC` hoặc `NFKD` cho toàn bộ database mà chưa có quyết định thiết kế/di trú rõ ràng.

## 7. Ví dụ Java 17+: normalization thay đổi chuỗi, collation thay đổi phép so sánh

Tạo file **`NormalizationVsCollationDemo.java`**:

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;

public class NormalizationVsCollationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String wide = "\uFF21";
        String plain = "A";

        System.out.println("raw accent equals: "
                + composed.equals(decomposed));
        System.out.println("NFC accent equals: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                    .equals(Normalizer.normalize(
                            decomposed, Normalizer.Form.NFC)));

        System.out.println("NFD width equals: "
                + Normalizer.normalize(wide, Normalizer.Form.NFD)
                    .equals(Normalizer.normalize(
                            plain, Normalizer.Form.NFD)));
        System.out.println("NFKD width equals: "
                + Normalizer.normalize(wide, Normalizer.Form.NFKD)
                    .equals(Normalizer.normalize(
                            plain, Normalizer.Form.NFKD)));

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        System.out.println("collator accent equal: "
                + (collator.compare(composed, decomposed) == 0));
        System.out.println("String still different: "
                + !composed.equals(decomposed));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 NormalizationVsCollationDemo.java
java NormalizationVsCollationDemo
```

Output trong môi trường JDK 24 đã kiểm tra:

```text
raw accent equals: false
NFC accent equals: true
NFD width equals: false
NFKD width equals: true
collator accent equal: true
String still different: true
```

**Kết luận của ví dụ:** normalization và collation đều quan tâm tới các quan hệ Unicode, nhưng có **đầu ra/hợp đồng khác nhau**. `Normalizer` tạo các `String` để so sánh/tái sử dụng, còn `Collator.compare` chỉ trả một quan hệ thứ tự. Gọi `compare` không sửa hai chuỗi gốc.

## 8. Dấu tiếng Việt: phân rã không đồng nghĩa xóa dấu

Tiếng Việt có nhiều dấu thanh và dấu cấu tạo chữ. Ví dụ chữ `ấ` có thể có dạng được cấu thành từ một hoặc nhiều ký tự kết hợp khác nhau theo Unicode, trong đó chuẩn hóa canonical giúp đối chiếu các biểu diễn tương đương.

Tuy nhiên:

- **Phân rã dấu:** tách các thành phần mã Unicode, ví dụ `ấ` thành các thành phần canonical khi áp dụng `NFD`.
- **Bỏ dấu:** loại bỏ các combining marks theo một chính sách riêng, **không phải** chức năng mặc định của `Collator.CANONICAL_DECOMPOSITION` hay `Normalizer.normalize(..., NFD)`.
- **So sánh không nhấn mạnh dấu:** có thể cân nhắc `Collator.PRIMARY` cho một số chức năng tìm kiếm, nhưng thứ tự và mức phân biệt cụ thể phụ thuộc locale.

Không tự dùng regex xóa tất cả marks làm phương pháp so sánh tiếng Việt chung, vì có thể làm nhiều từ phân biệt nghĩa trở nên trùng nhau. Một ứng dụng tìm kiếm cho phép người dùng gõ không dấu có thể dùng một chỉ mục phục vụ tìm kiếm, song vẫn cần giữ chuỗi gốc để hiển thị chính xác.

### 8.1. Khi nào dùng strength PRIMARY?

Nếu giao diện có chức năng “tìm gần đúng” hoặc sắp xếp không cần nhấn mạnh sự khác biệt dấu, `Collator.PRIMARY` là một lựa chọn để **thử nghiệm**. Nhưng mức PRIMARY còn có thể bỏ qua phân biệt hoa/thường hoặc một số biến thể theo locale. Nó không phải bộ chuẩn hóa key kỹ thuật hay bộ chuyển Unicode không có dấu.

Nếu người dùng cần phân biệt `ma`, `má` và `mà` vì lý do ngữ nghĩa, hãy cân nhắc `SECONDARY` hoặc `TERTIARY` và kiểm thử trên từ thực tế. **Decomposition xác định cách biểu diễn ký tự được chuẩn bị, không quyết định dấu có được phân biệt hay không.**

## 9. Minh họa độc lập cho strength và decomposition

Tạo file **`CollatorStrengthDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator c = Collator.getInstance(Locale.US);
        c.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        int[] strengths = {
                Collator.PRIMARY, Collator.SECONDARY,
                Collator.TERTIARY, Collator.IDENTICAL
        };
        String[] names = {
                "PRIMARY", "SECONDARY",
                "TERTIARY", "IDENTICAL"
        };

        for (int i = 0; i < strengths.length; i++) {
            c.setStrength(strengths[i]);

            System.out.println(names[i]
                    + " | composed-vs-decomposed="
                    + (c.compare("\u00E9", "e\u0301") == 0)
                    + " | accented-vs-plain="
                    + (c.compare("\u00E9", "e") == 0)
                    + " | upper-vs-lower="
                    + (c.compare("E", "e") == 0));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
```

Đầu ra đã kiểm tra trong môi trường `Locale.US`/JDK 24:

```text
PRIMARY | composed-vs-decomposed=true | accented-vs-plain=true | upper-vs-lower=true
SECONDARY | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=true
TERTIARY | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=false
IDENTICAL | composed-vs-decomposed=true | accented-vs-plain=false | upper-vs-lower=false
```

Ở mọi mức strength, hai biểu diễn của **cùng một chữ có dấu** vẫn bằng nhau do canonical decomposition. Nhưng `é` và `e` chỉ được xem bằng nhau ở `PRIMARY` của provider thử nghiệm, còn `E` và `e` được phân biệt ở `TERTIARY` trở lên.

**Thứ tự thực hành hợp lý:** cố định locale → xác định strength theo yêu cầu tìm/sắp xếp → xác định decomposition theo chất lượng Unicode đầu vào → kiểm tra các ví dụ biên. Không dùng một số strength hoặc decomposition được tìm thấy tình cờ trên máy phát triển làm hợp đồng chuẩn cho mọi môi trường.

## 10. NO_DECOMPOSITION không có nghĩa “không bao giờ xử lý dấu”

Tài liệu `RuleBasedCollator` lưu ý nó có thể đưa các biến thể **precomposed** và **combining-character** vào bảng luật ngay khi tạo bảng collation. Vì vậy:

1. Một cặp như `é` và `e + dấu sắc` có thể được coi tương đương **ngay ở NO_DECOMPOSITION** nếu bảng luật đã hỗ trợ ánh xạ đó, đặc biệt ở mức strength thấp.
2. Dấu kết hợp có **thứ tự canonical không chuẩn** là tình huống quan trọng cần `CANONICAL_DECOMPOSITION` hoặc `FULL_DECOMPOSITION` để bảo đảm xử lý đúng.
3. Các ký tự **compatibility** như full-width/half-width thường đòi hỏi `FULL_DECOMPOSITION` nếu muốn so sánh theo dạng phân rã tương thích.

Đừng xây kiểm thử dựa trên giả định “NO luôn khác, CANONICAL luôn bằng” cho mọi cặp và mọi locale/provider. Test đúng phải phản ánh **yêu cầu sản phẩm** và runtime được hỗ trợ. Với dữ liệu người dùng quốc tế không được kiểm soát hoàn toàn, `CANONICAL_DECOMPOSITION` thường là điểm bắt đầu hợp lý hơn NO.

## 11. CollationKey, sorting và tính nhất quán của cấu hình

Khi sắp xếp lượng lớn chuỗi nhiều lần, `Collator.getCollationKey(text)` có thể giúp tránh tính toán lại phép collation mỗi lần so sánh. Nhưng:

- Chỉ so sánh các `CollationKey` tạo từ **collator có cùng cấu hình**: locale, strength, decomposition, provider và dữ liệu collation tương thích.
- Không đổi `setStrength`/`setDecomposition` giữa lúc tạo các key rồi trộn chúng trong cùng một phép sort.
- Collation keys là dữ liệu nội bộ dùng cho collation, **không phải format dữ liệu chuẩn để lưu lâu dài giữa các phiên bản JDK**.
- Nếu collator xem hai chuỗi bằng nhau, các key so sánh bằng nhau về thứ tự, nhưng hai chuỗi vẫn có thể khác nhau theo `String.equals`.

`Collator` là mutable và không bảo đảm dùng đồng thời an toàn nếu nhiều thread thay đổi cấu hình; tài liệu khuyến nghị lấy **instance riêng cho mỗi thread** khi cần. Có thể `clone()` một cấu hình chuẩn để tạo instance cho tác vụ, hoặc tạo mới theo yêu cầu. Không thay đổi một collator dùng chung trên server khi mỗi request có locale và strength khác nhau.

### Bẫy TreeSet/TreeMap

`TreeSet<String>` với comparator là `Collator` dùng `compare(a,b)==0` để quyết định hai phần tử có cùng vị trí theo thứ tự sắp xếp. Nếu `Collator.PRIMARY` coi `"e"` và `"é"` bằng nhau, việc thêm cả hai có thể khiến set chỉ giữ một phần tử. Điều này có thể **khác `String.equals`**, gây bất ngờ hoặc mất dữ liệu nếu bạn đang coi set là tập hợp ID duy nhất.

Dùng collation cho **sắp xếp và tìm kiếm ngôn ngữ**, không tự dùng làm quy tắc **duy nhất/định danh**. Khi muốn sắp xếp có thứ tự tổng ổn định mà vẫn phân biệt các chuỗi khác nhau, có thể thêm tie-breaker bằng `String.compareTo` (hoặc ID bất biến) theo hợp đồng, nhưng cần suy nghĩ kỹ xem collation equality có cần được giữ như một nhóm riêng.

## 12. Chuẩn hóa trước khi lưu hay chuẩn hóa chỉ để so sánh?

Đây là quyết định kiến trúc quan trọng:

| Mục tiêu | Hướng xử lý | Cần chú ý |
| --- | --- | --- |
| So sánh/sắp xếp tên theo ngôn ngữ | `Collator(locale)` với strength/decomposition đã chọn | Locale/provider ảnh hưởng kết quả |
| Bảo đảm hai dạng canonical tương đương của chuỗi có cùng dạng lưu | `Normalizer.normalize(s, NFC)` tại ranh giới dữ liệu phù hợp | Cần quy chuẩn hóa và migration dữ liệu cũ nếu thay đổi |
| Xây chỉ mục tìm kiếm bỏ qua một số khác biệt văn bản | Một trường/index riêng cho tìm kiếm | Không xóa bản gốc, phải xác định các khác biệt chấp nhận bỏ qua |
| So sánh mã kỹ thuật chính xác | `String.equals` hoặc so sánh bytes theo encoding | Không dùng `Collator.PRIMARY` |
| Đối chiếu compatibility variants | `FULL_DECOMPOSITION` hoặc normalization compatibility có chủ đích | Có thể gộp các hình thức từng là khác biệt nghiệp vụ |
| So sánh không phân biệt chữ hoa/thường | Định nghĩa chính sách locale/case-folding/collation rõ ràng | Không mặc định lowercasing thay thế mọi phép so sánh |
| Lưu và đối chiếu password/token | Tuân thủ chuẩn bảo mật/normalization được hệ thống quy định | Không tự bật FULL hoặc PRIMARY làm giảm phân biệt |

Nếu quy trình chỉ cần **so sánh tại chỗ**, collator có thể là đủ và không cần biến đổi dữ liệu gốc. Nếu nhiều thành phần của hệ thống phải lưu **một dạng Unicode chuẩn thống nhất**, normalization ở ranh giới nhập dữ liệu có thể hữu ích. Nhưng đừng normalize toàn bộ nội dung dữ liệu sẵn có mà không đánh giá nguy cơ collision, tương thích ngược và hợp đồng API.

### NFC khác NFD và NFKC/NFKD

- `NFC` giữ tương đương canonical rồi **tổ hợp** các ký tự khi có thể; thường dễ dùng trong biểu diễn văn bản.
- `NFD` **phân rã canonical**, ví dụ `é` thành `e + dấu sắc`.
- `NFKC`/`NFKD` xét thêm **compatibility** và có thể gộp các kiểu chữ chỉ khác định dạng.

`Collator.CANONICAL_DECOMPOSITION` được mô tả tương ứng với **NFD**, còn `FULL_DECOMPOSITION` tương ứng **NFKD**, không phải NFC/NFKC; tất cả vẫn phải được hiểu trong ngữ cảnh **collation**. Bạn có thể chuẩn hóa chuỗi theo NFC để lưu và vẫn dùng Collator với canonical decomposition để bảo đảm so sánh đúng khi nhận đầu vào chưa chuẩn hóa.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Xem `NO_DECOMPOSITION` như lựa chọn mặc định luôn đúng | Văn bản có dấu/combining marks có thể được so sánh không đúng | Kiểm thử canonical equivalence; cân nhắc CANONICAL |
| Nghĩ `CANONICAL_DECOMPOSITION` nghĩa là bỏ dấu | Decomposition khác việc bỏ qua accent differences | Chọn `strength` đúng và kiểm thử tiếng Việt |
| Nghĩ `FULL_DECOMPOSITION` luôn tốt hơn | Compatibility folding có thể gộp phân biệt quan trọng | Chỉ dùng khi yêu cầu so sánh compatibility variants |
| Suy ra `compare==0` thì `String.equals==true` | Collation equivalence có thể rộng hơn byte/code-unit equality | Dùng `equals` cho dữ liệu cần exact |
| Dùng `String.equals` để sắp xếp theo ngôn ngữ | So sánh code units không có luật ngôn ngữ | Dùng Collator/Comparator phù hợp |
| Bật PRIMARY để tìm kiếm rồi dùng luôn làm khóa duy nhất | Nhiều từ khác dấu/case có thể bị gộp | Giữ ID và unique constraints tách riêng |
| Trộn strength với decomposition | Hai trục độc lập | Xác định rõ cả hai trong cấu hình |
| Tin rằng NO chắc chắn phân biệt mọi precomposed/combining pair | RuleBasedCollator có thể tự sinh ánh xạ | Đọc hợp đồng implementation và kiểm thử |
| Giả định getInstance trả cùng collator trên mọi JDK | Locale provider/data thay đổi | Ghim runtime nếu cần reproducibility |
| Chia sẻ collator mutable và thay đổi theo request | Có thể rò cấu hình giữa thread | Tạo/copy instance mỗi task hoặc đồng bộ hóa |
| Lưu CollationKey rồi so sánh qua các phiên bản | Không có hợp đồng serialization ổn định cho key | Chỉ dùng key trong phạm vi cấu hình/runtime phù hợp |
| Dùng NFKD/NFKC cho mọi chuỗi vô điều kiện | Có thể gộp full-width, ligatures, ký tự hình thức | Thiết kế policy normalization theo miền dữ liệu |
| Dùng một bộ quy tắc để xử lý secret và tên người | Ràng buộc bảo mật khác collation UI | Tách chính sách định danh khỏi hiển thị |
| Không kiểm thử tiếng Việt có dấu | Dễ bỏ sót lỗi thứ tự dấu và canonical forms | Có bộ dữ liệu thực tế, cả dạng NFC/NFD |

## 14. Ma trận kiểm thử khuyến nghị

Với một tính năng sắp xếp hoặc tìm kiếm đa ngôn ngữ, nên kiểm thử tối thiểu:

1. **Canonical equivalents:** `"\u00E9"` với `"e\u0301"`, thêm các chữ Việt tổ hợp dấu. Với canonical decomposition, các biểu diễn cùng canonical equivalence nên được so sánh phù hợp.
2. **Compatibility equivalents:** `"Ａ"` với `"A"` và `"ﬀ"` với `"ff"`; quyết định có cho phép coi bằng nhau không.
3. **Accent differences:** `"e"` với `"é"` và ví dụ tiếng Việt như `"ma"`/`"má"`; kiểm tra các strength khác nhau.
4. **Case differences:** `"e"` với `"E"`, và các chữ có ngữ cảnh Unicode đặc biệt.
5. **Combining order:** các chuỗi dấu kết hợp có thứ tự canonical khác nhau; kiểm tra chế độ phân rã.
6. **Locale:** `Locale.US`, `vi-VN` và những locale sản phẩm hỗ trợ thật sự.
7. **Null/empty/bad input:** xử lý tường minh `null` trước khi gọi `compare`; kiểm tra chuỗi trống và dữ liệu Unicode bị lỗi nếu nguồn có thể chứa chúng.
8. **Multithreading:** không có thread này thay strength/decomposition của collator đang được thread khác dùng.
9. **Phiên bản JDK/provider:** snapshot hoặc invariant test trong môi trường được cố định; không đưa ra kết luận phổ quát từ một runtime.
10. **Tính toàn vẹn dữ liệu:** so sánh collation bằng nhau không tự hợp nhất record/identifier nếu nghiệp vụ yêu cầu phân biệt.

Với các kiểm thử trên, cần ghi rõ **locale, strength, decomposition, JDK/provider** và dữ liệu Unicode đầu vào; một biểu thức `compare==0` đơn lẻ không đủ để giải thích nguyên nhân của hành vi.

## 15. Câu hỏi ôn tập

**Câu 1.** `Collator.CANONICAL_DECOMPOSITION` có tương đương với “bỏ dấu tiếng Việt” không?

**Đáp án:** Không. Nó giúp xử lý các biểu diễn **canonical-equivalent**, trong khi việc dấu có được phân biệt khi so sánh hay không do **strength** và luật locale quyết định.

**Câu 2.** Khi nào `FULL_DECOMPOSITION` có thể cho kết quả khác `CANONICAL_DECOMPOSITION`?

**Đáp án:** Với các ký tự có **compatibility decomposition**, ví dụ `Ａ` so với `A`, ligature `ﬀ` so với `ff`. Canonical decomposition không nhất thiết gộp những dạng này.

**Câu 3.** `Normalizer.Form.NFC` và `Collator.CANONICAL_DECOMPOSITION` có cùng tác dụng?

**Đáp án:** Không. NFC tạo ra `String` đã chuẩn hóa theo canonical composition; `Collator.CANONICAL_DECOMPOSITION` cấu hình phép so sánh theo canonical decomposition (quan hệ với NFD). Collator không trả về chuỗi normalized.

**Câu 4.** Vì sao cặp `"é"` và `"e\u0301"` đôi khi vẫn so sánh bằng nhau ở `NO_DECOMPOSITION`?

**Đáp án:** `RuleBasedCollator` có thể xây sẵn ánh xạ precomposed và combining forms trong bảng luật, và strength thấp có thể bỏ qua các khác biệt. Không dùng kết quả đó để kết luận NO luôn xử lý mọi canonical equivalence đúng.

**Câu 5.** Khi `Collator.PRIMARY` cho `compare(a,b)==0`, có được xóa một trong hai record không?

**Đáp án:** Không mặc định. Đó chỉ là tương đương **theo collation strength**, không nhất thiết là cùng identifier. Quy tắc duy nhất phải do miền nghiệp vụ xác định.

**Câu 6.** Dữ liệu được chuẩn hóa NFC lúc lưu rồi, có còn cần cân nhắc decomposition của Collator không?

**Đáp án:** Có. Nguồn dữ liệu khác có thể chưa được chuẩn hóa, và locale/provider có yêu cầu collation riêng. Nếu toàn bộ đường dữ liệu đã có hợp đồng normalization, có thể đánh giá tối ưu hiệu năng nhưng phải kiểm thử.

**Câu 7.** Có nên dùng `FULL_DECOMPOSITION + PRIMARY` cho mật khẩu để dễ gõ hơn không?

**Đáp án:** Không tự ý. Đây là thiết lập phục vụ collation ngôn ngữ, có thể gộp nhiều chuỗi khác nhau. Mật khẩu phải tuân thủ quy tắc xử lý đầu vào và so sánh bảo mật được hệ thống xác định.

## 16. Kết luận

- `Collator` so sánh văn bản **theo locale**; `Normalizer` tạo **dạng chuỗi Unicode chuẩn hóa**.
- Ba chế độ: **NO_DECOMPOSITION** (không phân rã), **CANONICAL_DECOMPOSITION** (tương đương `NFD`), **FULL_DECOMPOSITION** (tương đương `NFKD`).
- **Strength** và **decomposition** là hai điều khiển khác nhau. Decomposition không có nghĩa tự bỏ dấu hoặc bỏ phân biệt hoa/thường.
- `compare(...)==0` không chứng minh `String.equals(...)`; collation equivalence không thay thế định danh chính xác.
- Chọn decomposition theo nguồn dữ liệu và mục đích xử lý, kiểm thử văn bản có dấu/combining marks/compatibility characters, giữ cấu hình collator nhất quán trong quá trình sắp xếp.

**Tài liệu chính thức:**

- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html)
- [Java SE 21 — RuleBasedCollator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/RuleBasedCollator.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode UAX #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
