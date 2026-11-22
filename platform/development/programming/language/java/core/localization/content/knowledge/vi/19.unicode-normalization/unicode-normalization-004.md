# `Normalizer.isNormalized` và cách chọn chính sách chuẩn hóa Unicode trong Java

## 1. Vì sao hai chuỗi nhìn giống nhau vẫn có thể khác nhau?

Một giao diện Java có thể nhận tên người, nội dung tìm kiếm, thông điệp bản địa hóa hoặc dữ liệu sao chép từ nhiều thiết bị. Unicode cho phép một số ký tự nhìn tương tự hoặc có ý nghĩa tương đương được biểu diễn bằng **những chuỗi code point khác nhau**.

Ví dụ chữ `é` có ít nhất hai biểu diễn thường gặp:

```text
Biểu diễn dựng sẵn (precomposed):  U+00E9
Biểu diễn phân rã (decomposed):  U+0065 U+0301
                                 chữ e  dấu sắc kết hợp
```

Hai chuỗi có thể hiển thị giống nhau, nhưng Java `String.equals` so sánh **nội dung chuỗi theo đơn vị mã UTF-16**, không tự chuẩn hóa Unicode:

```java
String precomposed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(precomposed.equals(decomposed)); // false
```

Nếu ứng dụng lấy chuỗi đầu vào làm khóa tìm kiếm, khóa cache, tên người dùng hoặc giá trị cần so khớp, biểu diễn khác nhau có thể gây ra kết quả khác mong muốn.

Java cung cấp `java.text.Normalizer` với hai phương thức quan trọng:

```java
Normalizer.normalize(text, Normalizer.Form.NFC)
Normalizer.isNormalized(text, Normalizer.Form.NFC)
```

- `normalize` trả **chuỗi được chuẩn hóa** theo một form đã chọn.
- `isNormalized` trả **boolean** cho biết chuỗi đầu vào **đã ở form đó hay chưa**. Phương thức này **không sửa và không trả chuỗi mới**.
- Chính sách chuẩn hóa (**chọn form nào, ở lớp nào, cho loại dữ liệu nào**) là quyết định của sản phẩm, không phải do `Normalizer` tự quyết định.

**Trọng tâm:** kiểm tra đã chuẩn hóa bằng `isNormalized` chỉ có ý nghĩa khi bạn đã xác định **form phù hợp cho loại dữ liệu**. Không tồn tại một chính sách duy nhất luôn đúng cho tên hiển thị, tìm kiếm, mật khẩu, mã định danh và tài liệu pháp lý.

## 2. Các khái niệm phải phân biệt

### Code point, code unit và ký tự người dùng nhìn thấy

Unicode định nghĩa **code point** như `U+00E9`; Java `String` lưu các đơn vị mã **UTF-16**. Một code point ngoài vùng BMP có thể chiếm hai `char` (surrogate pair). Một ký tự người dùng nhìn thấy (*grapheme cluster*) có thể là **nhiều code point** (ví dụ chữ cơ sở kèm dấu kết hợp).

Do đó:

- `String.length()` đếm **đơn vị mã UTF-16**, không phải “chữ cái” hay grapheme.
- `String.codePoints()` duyệt Unicode code point, nhưng cũng không tự chia thành grapheme.
- `String.equals()` không tự thực hiện canonical equivalence, case folding hay collation.
- Chuẩn hóa Unicode có thể **thay đổi số code point và độ dài UTF-16** trong khi hình thức hiển thị gần như không đổi.

Ví dụ `"\u00E9".length() == 1`, nhưng `"e\u0301".length() == 2`. Việc chuẩn hóa có thể làm lệch chỉ số caret, vị trí đánh dấu lỗi và offset trong dữ liệu gốc. Nếu ứng dụng cần ánh xạ vị trí giữa bản gốc và bản chuẩn hóa, phải thiết kế riêng; không được giả sử index vẫn y nguyên.

### Canonical equivalence và compatibility equivalence

**Canonical equivalence**: các chuỗi được Unicode coi là những cách mã hóa tương đương về mặt chính tả của cùng nội dung, như `U+00E9` và `U+0065 U+0301`.

**Compatibility equivalence**: có thêm những ký tự khác biệt về **kiểu trình bày hoặc quy ước biểu diễn**, nhưng có thể được ánh xạ tới một dạng cơ bản khi cần xử lý tương thích. Ví dụ:

```text
U+FF21 (Ａ, fullwidth A) → A   với compatibility normalization
U+FB03 (ﬃ, ligature)   → ffi
U+2460 (①, circled 1)  → 1
```

Các ánh xạ compatibility **có thể làm mất khác biệt có ý nghĩa** trong tên thương hiệu, dữ liệu nghiên cứu, ký hiệu toán học hoặc bản gốc cần lưu giữ. Không nên đồng nhất “được Unicode cho phép chuẩn hóa” với “đúng cho nghiệp vụ”.

## 3. Bốn form trong `Normalizer.Form`

Java cung cấp enum `java.text.Normalizer.Form` với bốn lựa chọn:

| Form | Tên | Hành vi chính | Ví dụ sử dụng có cân nhắc |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Phân rã các ký tự có phân rã **canonical**, sắp xếp dấu kết hợp theo thứ tự quy tắc | Phân tích thành phần dấu/ký tự, một số bước xử lý nội bộ |
| `NFC` | Canonical Decomposition rồi Composition | Chuẩn hóa canonical và tổ hợp lại khi quy tắc cho phép | Lưu văn bản hiển thị thông thường, so khớp canonical |
| `NFKD` | Compatibility Decomposition | Phân rã cả canonical lẫn compatibility | Một số pipeline xử lý/search đặc biệt, có khả năng mất phân biệt |
| `NFKC` | Compatibility Decomposition rồi Canonical Composition | Gom các dạng compatibility rồi tổ hợp canonical khi có thể | Khóa tìm kiếm được xác định rõ, một số profile định danh theo tiêu chuẩn riêng |

Hãy hình dung hai trục:

```text
                     Phân rã                   Tổ hợp lại khi được phép
Canonical            NFD                        NFC
Compatibility        NFKD                       NFKC
```

**NFC và NFD đều là canonical forms**, nhưng kết quả mã hóa không giống nhau. `NFKC` và `NFKD` đi xa hơn: chúng chấp nhận **compatibility mappings**, nên có thể gộp các cách trình bày vốn có ý nghĩa khác nhau.

Form không phải mức độ “đúng hơn/sạch hơn” theo thứ tự bốn bậc. **NFKC không phải NFC phiên bản luôn tốt hơn.** Mỗi form có hợp đồng ngữ nghĩa riêng.

### Ví dụ chữ có dấu

```text
Input A: U+00E9
Input B: U+0065 U+0301

NFC(A)  = U+00E9
NFC(B)  = U+00E9

NFD(A)  = U+0065 U+0301
NFD(B)  = U+0065 U+0301
```

Với những trường hợp canonical equivalence này, chuẩn hóa **hai vế về cùng form** giúp việc so sánh `String.equals` có nghĩa hơn.

### Ví dụ compatibility

```text
Input: ＡＢＣ１２３  (fullwidth)
NFC:   ＡＢＣ１２３  (giữ nguyên các khác biệt compatibility)
NFKC:  ABC123

Input: ﬃ
NFKC:  ffi

Input: ①
NFKC:  1
```

Nếu mã sản phẩm phân biệt ký tự `①` với số `1`, NFKC có thể **làm mất thông tin cần giữ**. Ngược lại, nếu công cụ tìm kiếm cố ý coi hai dạng ấy tương đương, một bản **search key riêng** theo NFKC có thể hữu ích.

## 4. `isNormalized` hoạt động như thế nào?

Chữ ký API:

```java
public static boolean isNormalized(
        CharSequence src,
        Normalizer.Form form)
```

`src` là chuỗi hoặc `CharSequence` cần kiểm tra; `form` là một trong bốn giá trị của `Normalizer.Form`. Kết quả chỉ nói về **form đã chỉ định**, không có nghĩa “chuỗi đã chuẩn hóa theo mọi form”.

Ví dụ:

```java
String text = "e\u0301";

boolean alreadyNfc =
        Normalizer.isNormalized(text, Normalizer.Form.NFC);
boolean alreadyNfd =
        Normalizer.isNormalized(text, Normalizer.Form.NFD);
```

Với dữ liệu trên, `alreadyNfc` là `false`, còn `alreadyNfd` là `true`. Một chuỗi đang đúng NFD không đồng nghĩa nó cũng đúng NFC.

**Khác biệt với `normalize`:**

```java
boolean check = Normalizer.isNormalized(text, Normalizer.Form.NFC);
String result = Normalizer.normalize(text, Normalizer.Form.NFC);
```

- `check`: **kiểm tra** điều kiện, không tạo phiên bản chuẩn hóa để lưu.
- `result`: **lấy giá trị** đã chuyển sang form yêu cầu; chuỗi `text` không bị sửa.
- Nếu `check == true`, về nội dung Unicode, chuỗi đó đã thỏa form. Có thể giữ nguyên giá trị thay vì gọi `normalize` nếu kiểm tra đó có ích cho luồng xử lý.
- **Không mặc định “kiểm tra trước rồi normalize” luôn tối ưu**: `isNormalized` cũng phải xem xét chuỗi; nếu phần lớn input cần chuyển đổi, hai lượt làm việc có thể tốn hơn normalize một lần. Hãy đo trên workload thực tế.

Với `src == null` hoặc `form == null`, API không trả một kết quả “chưa chuẩn hóa” thay thế; đầu vào null không hợp lệ và có thể gây `NullPointerException`. Nếu pipeline có trường optional, hãy xử lý null tại tầng dữ liệu/validation trước khi gọi API.

## 5. Chương trình độc lập: kiểm tra NFC/NFD và sự khác nhau của `String.equals`

Tạo tệp **`NormalizationInspectionDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizationInspectionDemo {
    private static String points(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("rawEquals=" +
                precomposed.equals(decomposed));
        System.out.println("precomposed.length=" +
                precomposed.length());
        System.out.println("decomposed.length=" +
                decomposed.length());

        System.out.println("precomposed NFC=" +
                Normalizer.isNormalized(
                        precomposed, Normalizer.Form.NFC));
        System.out.println("decomposed NFC=" +
                Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFC));
        System.out.println("decomposed NFD=" +
                Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFD));

        String a = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String b = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equal=" + a.equals(b));
        System.out.println("NFC codePoints=" + points(b));
        System.out.println("NFD codePoints=" + points(
                Normalizer.normalize(
                        precomposed, Normalizer.Form.NFD)));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 NormalizationInspectionDemo.java
java -cp . NormalizationInspectionDemo
```

Kết quả:

```text
rawEquals=false
precomposed.length=1
decomposed.length=2
precomposed NFC=true
decomposed NFC=false
decomposed NFD=true
NFC equal=true
NFC codePoints=U+00E9
NFD codePoints=U+0065 U+0301
```

**Giải thích:** `String.equals` không coi hai biểu diễn UTF-16 ban đầu là bằng nhau. Khi chuẩn hóa **cả hai về NFC**, chúng trở thành cùng một chuỗi và so sánh bằng `equals` trả `true`. Còn NFD tách ký tự thành `e` và dấu sắc kết hợp. Cần nhất quán form của **cả hai vế**, không chuẩn hóa một vế rồi đem so với vế chưa chuẩn hóa.

Dùng `codePoints()` để in `U+...` giúp nhìn rõ sự khác biệt mà mắt thường có thể khó nhận ra trên terminal hoặc giao diện.

## 6. Chương trình độc lập: vì sao `NFKC` có thể làm mất phân biệt?

Tạo **`CompatibilityNormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class CompatibilityNormalizationDemo {
    private static String nfkc(String source) {
        return Normalizer.normalize(
                source, Normalizer.Form.NFKC);
    }

    public static void main(String[] args) {
        String wide = "\uFF21\uFF22\uFF23\uFF11\uFF12\uFF13";
        String ligature = "\uFB03";
        String circledOne = "\u2460";

        System.out.println("wide NFC=" +
                Normalizer.isNormalized(
                        wide, Normalizer.Form.NFC));
        System.out.println("wide NFKC=" + nfkc(wide));
        System.out.println("ligature NFKC=" + nfkc(ligature));
        System.out.println("circled NFKC=" + nfkc(circledOne));

        String vietnameseD = "\u0111";
        System.out.println("d-stroke NFD unchanged=" +
                vietnameseD.equals(Normalizer.normalize(
                        vietnameseD, Normalizer.Form.NFD)));

        String latinA = "a";
        String cyrillicA = "\u0430";
        System.out.println("confusable equality=" +
                nfkc(latinA).equals(nfkc(cyrillicA)));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CompatibilityNormalizationDemo.java
java -cp . CompatibilityNormalizationDemo
```

Đầu ra:

```text
wide NFC=true
wide NFKC=ABC123
ligature NFKC=ffi
circled NFKC=1
d-stroke NFD unchanged=true
confusable equality=false
```

Các điểm cần rút ra:

- `wide NFC=true`: ký tự fullwidth có thể **đã ở NFC**, nhưng NFKC sẽ chuyển nó sang dạng ASCII tương ứng. Vì vậy `isNormalized(text, NFC)` **không** nói được `normalize(text, NFKC)` có đổi nó hay không.
- Ligature `ﬃ` trở thành `ffi`, ký tự `①` trở thành `1`; sự khác biệt kiểu trình bày đã mất ở bản NFKC.
- Chữ `đ` (`U+0111`) không tự tách thành `d` cộng một dấu rồi biến mất: normalize về NFD **không phải thuật toán bỏ dấu tiếng Việt**.
- Chữ Latin `a` và chữ Cyrillic `а` (`U+0430`) có thể rất giống nhau về hình thức nhưng **vẫn khác nhau sau NFKC**. **Unicode normalization không phải bộ phát hiện mọi ký tự dễ gây giả mạo (confusable characters)**.

## 7. Cách chọn chính sách chuẩn hóa theo mục đích dữ liệu

Thay vì “normalize tất cả về NFKC” ngay khi nhận input, nên xác định **data contract** cho từng loại chuỗi.

| Loại dữ liệu | Chính sách khởi đầu đáng cân nhắc | Lý do / lưu ý |
| --- | --- | --- |
| Văn bản hiển thị thông thường | Thường chọn **NFC** cho bản lưu đã xử lý, đồng thời bảo tồn nguồn khi cần | Thống nhất canonical equivalence, ít can thiệp hơn compatibility normalization |
| Dữ liệu dịch `ResourceBundle` | NFC nhất quán trong pipeline xuất bản nếu có yêu cầu; giữ nguyên ý nghĩa và placeholder | Tránh khác biệt mã hóa không chủ đích; không tự “sửa” ngữ pháp |
| Trường tìm kiếm tên/sản phẩm | Tạo **search key riêng**, có thể NFC hoặc NFKC kèm phép so sánh/ngôn ngữ phù hợp | Muốn khớp rộng nhưng phải kiểm soát những phân biệt bị gộp |
| Username/identifier | Theo **profile/hợp đồng định danh đã công bố**, không tự chọn NFKC tùy tiện | Chuẩn hóa có thể khiến hai định danh khác nhau trùng nhau; yêu cầu migration và kiểm soát tính duy nhất |
| Mật khẩu và bí mật opaque | **Không tự ý thay đổi**; tuân thủ giao thức xác thực và chính sách hai phía đã quy định | Thay đổi input trước hashing có thể làm mật khẩu cũ không còn kiểm tra được |
| Dữ liệu cần giữ nguyên (chữ ký số, bằng chứng, code, tài liệu pháp lý) | Bảo tồn bản gốc; nếu cần normalized view thì tạo **bản dẫn xuất** | Chuẩn hóa có thể làm đổi byte, hash và ý nghĩa trình bày |
| URL/domain/email | Tuân theo quy tắc của **chuẩn và thành phần tương ứng**, không lấy `NFKC` làm validator | IDNA, chuẩn URL/email và security checks không thể thay bằng normalize đơn thuần |
| Khóa nội bộ sinh tự động chỉ dùng ASCII | Có thể **từ chối** Unicode ngoài hợp đồng thay vì ép về ASCII | Tránh mapping âm thầm và va chạm định danh |

**Khuyến nghị thiết kế tổng quát:** bảo tồn dữ liệu gốc khi có giá trị kiểm toán/hiển thị; tạo **dạng canonical cho nghiệp vụ cần so sánh**; nêu rõ form và version/chính sách để mọi điểm nhập và tra cứu áp dụng nhất quán.

### 7.1. Chính sách hiển thị

Nếu giao diện nhận văn bản tự nhiên, NFC thường là lựa chọn hợp lý để đưa các chuỗi canonical tương đương về một biểu diễn thống nhất. Nhưng không nên dùng NFC như phép “làm sạch” tất cả dữ liệu: nó không xác thực cú pháp, không xóa control characters, không kiểm tra ngôn ngữ đúng, không ngăn mã độc.

Với nội dung phải bảo tồn byte chính xác (chữ ký, dữ liệu gốc từ bên ngoài), hãy lưu **bản gốc** và tạo **bản chuẩn hóa dẫn xuất** khi cần. Đừng chuẩn hóa rồi ghi đè mất dữ liệu ban đầu mà không được phép.

### 7.2. Chính sách tìm kiếm

Một hệ thống có thể cho phép người dùng nhập fullwidth `ＡＢＣ` để tìm `ABC`. Tạo search key bằng NFKC có thể giúp gộp biến thể đó, nhưng kết quả còn phụ thuộc **case folding, so khớp dấu, ngôn ngữ, tách từ** và hành vi truy vấn.

Thường nên có ít nhất hai trường logic:

```text
originalText  → giữ để hiển thị / kiểm toán
searchKey     → tạo theo profile tìm kiếm đã chọn
```

**Không đổi cả nội dung hiển thị thành search key.** Với NFKC, ký tự `①` sẽ thành `1`, nên nếu ghi đè originalText, sản phẩm mất hình thức gốc.

### 7.3. Chính sách mã định danh

Giả sử cho phép hai tài khoản tên `ABC123` và `ＡＢＣ１２３` tồn tại. Nếu sau này áp NFKC khi kiểm tra trùng, cả hai có thể thành cùng một key. Đây là **va chạm định danh** cần kế hoạch chuyển đổi, không phải chuyện thay một dòng Java.

Trước khi thay chính sách ID:

1. Xác định danh sách ký tự cho phép và ý nghĩa các phép biến đổi.
2. Xác định liệu các biểu diễn trước đây được coi là cùng định danh hay khác nhau.
3. Kiểm tra dữ liệu cũ có collision sau chuẩn hóa.
4. Quy định **thứ tự validation và normalization** rõ ràng.
5. Thống nhất chính sách giữa đăng ký, đăng nhập, tra cứu, phân quyền, log và cơ sở dữ liệu.
6. Quản lý version/policy migration nếu đang vận hành hệ thống có người dùng thật.

Không dùng `isNormalized(..., NFC) == true` như bằng chứng một identifier “an toàn”, “hợp lệ” hoặc “không giả mạo”. Đó chỉ là câu trả lời về **normalization form**.

## 8. Chương trình độc lập: tách bản hiển thị, search key và validation

Ví dụ này minh họa ba quyết định có chủ đích:

- Bản hiển thị được chuyển về NFC để nhất quán canonical.
- Bản khóa tìm kiếm thử NFKC và `toLowerCase(Locale.ROOT)` như **một chính sách ví dụ rất đơn giản**.
- Mã tài khoản ASCII có hợp đồng riêng: **từ chối ký tự ngoài tập cho phép trước khi ép sang NFKC**.

Tạo **`NormalizationPolicyDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;

public class NormalizationPolicyDemo {
    private static String displayText(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFC);
    }

    private static String simpleSearchKey(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }

    private static boolean acceptsAsciiAccountId(String input) {
        return input != null
                && input.matches("[A-Za-z0-9_-]{3,20}");
    }

    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";
        String fullwidth = "\uFF21\uFF22\uFF23\uFF11\uFF12\uFF13";

        System.out.println("displaySameMeaning=" +
                displayText(composed).equals(displayText(decomposed)));

        System.out.println("searchSameMeaning=" +
                simpleSearchKey(composed)
                        .equals(simpleSearchKey(decomposed)));

        System.out.println("searchWide=" +
                simpleSearchKey(fullwidth));

        System.out.println("asciiOriginalAllowed=" +
                acceptsAsciiAccountId(fullwidth));

        System.out.println("asciiNormalizedAllowed=" +
                acceptsAsciiAccountId(Normalizer.normalize(
                        fullwidth, Normalizer.Form.NFKC)));

        String nfc = displayText(decomposed);
        System.out.println("idempotent=" +
                nfc.equals(displayText(nfc)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NormalizationPolicyDemo.java
java -cp . NormalizationPolicyDemo
```

Đầu ra:

```text
displaySameMeaning=true
searchSameMeaning=true
searchWide=abc123
asciiOriginalAllowed=false
asciiNormalizedAllowed=true
idempotent=true
```

**Cảnh báo quan trọng:** dòng `asciiNormalizedAllowed=true` cho thấy **tại sao không nên tự động normalize để “hợp thức hóa” một định danh không thỏa hợp đồng nhập liệu ban đầu**. Cùng một chuỗi fullwidth bị từ chối theo chính sách ASCII nghiêm ngặt, nhưng sẽ được chấp nhận nếu mã nguồn ngầm đổi nó sang ASCII trước khi kiểm tra. Ứng dụng phải chọn một trong hai chính sách và công bố/áp dụng nhất quán.

`simpleSearchKey` cũng không phải một bộ chuẩn hóa tìm kiếm cho mọi ngôn ngữ. `toLowerCase(Locale.ROOT)` **không tương đương hoàn toàn với Unicode full case folding**, không giải quyết tách từ, sự khác biệt giữa các chữ viết hay vấn đề thứ tự so sánh theo locale. Đây chỉ là bước dẫn xuất minh họa, cần điều chỉnh theo yêu cầu của công cụ tìm kiếm.

## 9. Quy trình `isNormalized` trong ứng dụng thật

### Khi chỉ cần kiểm tra policy

Nếu hợp đồng yêu cầu text lưu trữ **phải ở NFC**, có thể kiểm tra và từ chối input không đạt:

```java
boolean validForm =
        Normalizer.isNormalized(input, Normalizer.Form.NFC);
```

Trích đoạn yêu cầu `input` khác null và đã được xác định kiểu chuỗi. Nếu `validForm == false`, sản phẩm có thể:

- Yêu cầu client gửi lại NFC;
- Hoặc chuẩn hóa ở server, nếu hợp đồng cho phép;
- Hoặc lưu bản gốc riêng và bản NFC trong hai trường khác nhau.

Không phải lúc nào “không ở NFC” cũng là **lỗi dữ liệu người dùng**; đặc biệt nội dung văn bản tự nhiên có thể nhập hợp lệ bằng NFD.

### Khi cần chuyển đổi dữ liệu

```java
String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);
```

Đây là lựa chọn đơn giản khi pipeline đã xác định **luôn đưa về NFC**. Không cần gọi `isNormalized` trước chỉ để rồi luôn `normalize`: đó có thể là công việc trùng lặp.

### Khi muốn tránh chuyển đổi không cần thiết

```java
String normalized = Normalizer.isNormalized(
        input, Normalizer.Form.NFC)
        ? input
        : Normalizer.normalize(input, Normalizer.Form.NFC);
```

Đoạn này giữ `input` nếu nó đã ở NFC. Nó hữu ích khi code cần phân nhánh chính sách hoặc đo trạng thái chuẩn hóa. Nhưng về **hiệu năng**, việc quét kiểm tra rồi mới normalize không mặc định nhanh hơn; hãy benchmark dữ liệu thực tế.

### Tính chất idempotent

Nếu form và dữ liệu không thay đổi:

```text
normalize(normalize(x, form), form) == normalize(x, form)
```

Điều này nghĩa là áp dụng cùng một form thêm lần nữa không tiếp tục đổi **nội dung chuẩn hóa**. Nhưng không có nghĩa việc chuẩn hóa theo **hai form khác nhau** cũng giữ nguyên dữ liệu, ví dụ NFC rồi NFKC có thể tiếp tục thay đổi các ký tự compatibility.

## 10. Chuẩn hóa không phải bỏ dấu tiếng Việt

Một số hệ thống tìm kiếm muốn tìm `cafe` khi người dùng nhập `café`. Cần phân biệt **canonical normalization** và **diacritic-insensitive search**.

- `NFD` phân rã nhiều ký tự có dấu thành chữ cơ sở và dấu kết hợp, nhưng **vẫn giữ dấu**.
- Loại bỏ các ký tự thuộc nhóm Unicode `Mark` sau NFD là **một thao tác khác**, không phải một normal form.
- Cách loại dấu có thể tạo ra các chuỗi trùng nhau dù về ngữ nghĩa là khác nhau, và không xử lý được mọi chữ viết theo cùng cách.
- Trong tiếng Việt, `đ` không tự thành `d` chỉ bằng NFD. Một thuật toán gỡ dấu đơn giản có thể bỏ sót hoặc thay đổi không đồng đều.
- Bỏ dấu phù hợp cho một **search index phụ** có thể là lựa chọn nghiệp vụ, nhưng không nên áp dụng để thay thế văn bản gốc hay so khớp định danh nếu chưa có hợp đồng rõ ràng.

Khi cần so sánh theo quy tắc ngôn ngữ (sắp xếp tên, so khớp có/không phân biệt dấu hoặc chữ hoa theo locale), hãy nghiên cứu `java.text.Collator` hoặc một thư viện/search engine có hỗ trợ collation. `Normalizer` xử lý **biểu diễn Unicode**, **không phải** toàn bộ ngữ pháp và thứ tự sắp xếp của một ngôn ngữ.

## 11. Chuẩn hóa không phải lowercase và không phải bảo vệ chống giả mạo

Các khái niệm liên quan nhưng khác nhau:

| Thao tác | Câu hỏi giải quyết | Điều không tự giải quyết |
| --- | --- | --- |
| Unicode normalization | Hai biểu diễn Unicode có cần đưa về cùng canonical/compatibility form? | Không tự chuyển tất cả chữ hoa thành chữ thường |
| `toLowerCase(locale)` | Đổi kiểu chữ theo các quy tắc case mapping | Không phải full case folding, không tự chuẩn hóa Unicode |
| Full Unicode case folding | Định nghĩa khóa so khớp không phân biệt hoa/thường cho một profile tương ứng | Không phải API `String.toLowerCase` toàn năng |
| Locale-aware collation | Hai chuỗi được so sánh/sắp xếp theo quy ước ngôn ngữ ra sao? | Không thay thế validation hay xác thực |
| Identifier profile/security checks | Những ký tự nào hợp lệ, có gây nhầm lẫn/giả mạo không? | Không thể chỉ dùng `isNormalized` để kết luận |

Một ví dụ bảo mật dễ hiểu: chữ Latin `a` (`U+0061`) và chữ Cyrillic `а` (`U+0430`) có thể rất giống nhau bằng mắt thường, nhưng **NFKC không gộp chúng thành một chữ**. Điều đó chứng minh chuẩn hóa Unicode **không loại bỏ mọi homograph/confusable attack**.

Nếu ứng dụng cần kiểm tra identifier quốc tế, nên áp dụng profile bảo mật/cú pháp phù hợp, danh sách ký tự cho phép, quy tắc mixed-script và confusable detection khi cần; với tên miền, dùng chuẩn IDNA tương ứng. Đừng lấy `NFKC` như một “bộ lọc chống Unicode nguy hiểm”.

Tương tự, Unicode normalization không tự loại bỏ dấu điều khiển, định dạng hướng văn bản, ký tự zero-width hay mã độc trong HTML. Dữ liệu hiển thị trên web vẫn cần **escape theo ngữ cảnh đầu ra**; dữ liệu đầu vào cần validation riêng.

## 12. Chuẩn hóa với tiếng Việt và bản địa hóa

Bản tiếng Việt có thể chứa nhiều dấu thanh và dấu nguyên âm, đôi khi được biểu diễn theo nhiều code point. Ví dụ một chữ có dấu có thể có cả dạng dựng sẵn hoặc dạng gồm chữ/dấu kết hợp. Chuẩn hóa canonical giúp hệ thống có **biểu diễn thống nhất** khi lưu hoặc so sánh, nhưng cần hiểu:

1. **NFC không loại bỏ dấu**; nó tổ hợp lại theo những quy tắc Unicode cho phép.
2. Không phải mọi tổ hợp ký tự đều có một code point dựng sẵn. “Composition” không đồng nghĩa mọi grapheme sẽ trở thành một `char`.
3. Việc thay đổi thứ tự combining marks được quy định bởi canonical ordering; không được cố gán cách sắp dấu riêng bằng xử lý chuỗi tùy tiện.
4. Nếu ứng dụng đếm chữ, đặt caret hay highlight đoạn tìm kiếm, việc biến đổi chuỗi có thể thay đổi offset, nên cần ánh xạ vị trí hoặc thực hiện các bước xử lý ở một dạng nhất quán.
5. `ResourceBundle`, `MessageFormat` và các tài nguyên giao diện cần được kiểm thử theo **đúng Unicode của tệp nguồn và encoding khi build**, không chỉ dựa vào việc văn bản nhìn giống nhau trên IDE.

Java `Normalizer` không tự chọn `Locale.VIETNAM` để chuẩn hóa; **NFC/NFD/NFKC/NFKD không có tham số locale**. Quy tắc normalization là về Unicode, khác với cách sắp xếp, chuyển hoa-thường và cách diễn đạt theo từng ngôn ngữ.

## 13. Khi nào thực hiện chuẩn hóa trong pipeline?

Một thiết kế thường gặp:

```text
Nhận input
    ↓
Kiểm tra null, kiểu dữ liệu, giới hạn kích thước và encoding
    ↓
Xác định profile theo loại trường:
    - nội dung hiển thị
    - search key
    - identifier
    - mật khẩu/opaque
    ↓
Normalize nếu profile yêu cầu
    ↓
Validation theo profile trên giá trị phù hợp
    ↓
Lưu bản gốc/bản dẫn xuất theo contract
    ↓
Tra cứu và so sánh sử dụng cùng policy
```

Vị trí của normalize **trước hay sau validation** tùy mục đích:

- Với trường **chỉ chấp nhận ASCII chính xác**, hãy kiểm tra hợp đồng input trước khi một bước compatibility normalization có thể biến Unicode ngoài ASCII thành ASCII; nếu không, ứng dụng vô tình nới điều kiện chấp nhận.
- Với trường **cho phép nhiều biểu diễn Unicode nhưng muốn canonical comparison**, có thể chuẩn hóa trước khi so khớp/kiểm tra trùng, đồng thời validate profile ký tự đã cho phép.
- Với trường **định danh bảo mật**, cần xác định rõ thứ tự các bước và kiểm tra sự nhất quán toàn hệ thống; không có một thứ tự chung đúng cho mọi giao thức.
- Với **mật khẩu**, không được tùy tiện normalize rồi hash nếu hệ thống/giao thức không quy định; việc sửa policy sau khi có tài khoản cũ có thể làm đăng nhập thất bại hoặc đổi tính chất bảo mật.
- Với nội dung **ký số hoặc kiểm tra hash**, byte gốc và byte sau normalization thường khác nhau; đừng normalize một bên của giao thức mà bên còn lại không biết.

**Hợp đồng so sánh phải đồng bộ:** dữ liệu viết vào database, dữ liệu tra cứu và chỉ mục phải cùng được xử lý bởi một version của policy. Chuẩn hóa tại thời điểm query nhưng không chuẩn hóa index sẽ tạo “không tìm thấy” khó giải thích.

## 14. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| So sánh hai chuỗi Unicode bằng `equals` rồi nghĩ chúng hiển thị khác | Dạng dựng sẵn và phân rã có thể khác mã hóa | Normalize hai phía về cùng form nếu hợp đồng so sánh cần canonical equivalence |
| Gọi `isNormalized(text, NFC)` rồi tưởng trả chuỗi mới | Chỉ nhận `boolean` | Dùng `normalize(text, NFC)` để có chuỗi |
| Dùng NFKC cho toàn bộ văn bản gốc | Có thể đổi fullwidth, ligature, ký hiệu khoanh tròn... | Chọn policy theo trường; giữ bản gốc nếu có ý nghĩa |
| Chỉ kiểm tra `isNormalized(..., NFC) == true` để duyệt username | Không xác thực ký tự, script hoặc confusables | Thêm identifier profile và kiểm tra bảo mật |
| Dùng NFD để “xóa dấu” tiếng Việt | NFD giữ dấu ở dạng combining marks | Tách normalization khỏi xử lý tìm kiếm không phân biệt dấu |
| Gọi NFKC rồi nói đã xử lý mọi kiểu giả mạo | Nhiều chữ ở script khác vẫn dễ nhầm | Kiểm tra confusables/mixed-script theo profile thực tế |
| `toLowerCase(Locale.ROOT)` rồi coi là full Unicode casefold | Không tương đương mọi quy tắc case folding | Dùng engine/profile tương ứng nếu cần Unicode casefold đầy đủ |
| Normalize cả mật khẩu/opaque identifier mà chưa có quy tắc | Đổi ý nghĩa đầu vào và phá tương thích | Tuân thủ hợp đồng giao thức và lộ trình migration |
| Chỉ normalize lúc nhập mà không làm lúc so sánh | Key và query không cùng dạng | Dùng một pipeline chính sách thống nhất |
| Thay nội dung nguồn bằng bản chuẩn hóa rồi xóa bản gốc | Mất dấu vết audit và dữ liệu cần bảo tồn | Tách bản gốc và bản dẫn xuất |
| Tính độ dài/offset trước normalize rồi dùng cho bản sau | Highlight/caret/index sai | Tính lại hoặc ánh xạ offset giữa hai biểu diễn |
| Dựa vào form để suy ra tính hợp lệ ngữ pháp | Chuẩn hóa không chứng minh nội dung đúng | Thực hiện validation nghiệp vụ riêng |
| Xem `isNormalized` luôn là tối ưu hiệu năng | Có thể làm hai lần quét dữ liệu | Đo hiệu năng trước khi dùng nhánh kiểm tra |
| Bỏ qua khác biệt Unicode version/JDK | Bộ ký tự/quy tắc hỗ trợ có thể thay đổi theo runtime | Kiểm thử trên Java runtime mục tiêu, quản lý phiên bản chính sách |

## 15. Bộ kiểm thử nên có

Một pipeline chuẩn hóa cần thử những nhóm sau:

1. **Canonical equivalence:** `"\u00E9"` và `"e\u0301"` khác nhau trước normalize, bằng nhau sau cùng NFC hoặc NFD.
2. **Bốn forms:** kiểm tra `isNormalized` cho từng form, không suy ra từ kết quả của form khác.
3. **Compatibility characters:** fullwidth `Ａ`, ligature `ﬃ`, ký tự khoanh tròn `①`; xác nhận NFKC đổi khi policy cho phép.
4. **Dấu tiếng Việt:** nhiều dấu kết hợp, chữ `đ`, dữ liệu có thứ tự combining marks khác nhau; không tự mất dấu khi dùng canonical normalization.
5. **Idempotence:** normalize hai lần bằng cùng form cho cùng nội dung.
6. **Đồng nhất ghi/đọc:** cùng chính sách tại bước ghi database, tạo index và tìm kiếm.
7. **Không va chạm ID:** chạy thử dataset có `ABC123` và bản fullwidth trước khi chuyển policy về NFKC.
8. **Văn bản từ nhiều nguồn:** IME, copy/paste, di động, resource bundles, API và tệp có encoding khác nhau.
9. **Unicode ngoài BMP:** chuỗi có emoji/supplementary code points; kiểm tra offset tính theo UTF-16.
10. **Giới hạn đầu vào:** null, chuỗi rỗng, chuỗi rất dài, chuỗi kết hợp dấu bất thường; giới hạn kích thước có thể cần kiểm tra trước khi thực hiện xử lý nặng.
11. **Bảo mật:** confusables/mixed-script, ký tự điều khiển, bidi và zero-width; không tuyên bố normalization thay thế những bài kiểm tra này.
12. **Tính ổn định qua bản cập nhật:** quản lý thay đổi Unicode/JDK, reindex hoặc chuyển version policy có kiểm soát khi cần.

### Ví dụ kiểm tra đơn giản

Tạo tệp **`NormalizationAssertions.java`**:

```java
import java.text.Normalizer;

public class NormalizationAssertions {
    private static String nfc(String text) {
        return Normalizer.normalize(text, Normalizer.Form.NFC);
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Normalization check failed");
        }
    }

    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        require(!a.equals(b));
        require(nfc(a).equals(nfc(b)));
        require(Normalizer.isNormalized(nfc(b),
                Normalizer.Form.NFC));
        require(nfc(nfc(b)).equals(nfc(b)));
        require(Normalizer.normalize("\u2460",
                Normalizer.Form.NFKC).equals("1"));

        System.out.println("5 checks passed");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NormalizationAssertions.java
java -cp . NormalizationAssertions
```

Nếu đủ điều kiện:

```text
5 checks passed
```

Phương thức `require` dùng `AssertionError` trực tiếp nên không phụ thuộc JVM có bật tùy chọn `-ea` hay không.

## 16. Tóm tắt

- `Normalizer.isNormalized(text, form)` chỉ **kiểm tra** chuỗi đang ở form yêu cầu; `Normalizer.normalize(text, form)` **trả chuỗi đã chuẩn hóa**, không sửa chuỗi cũ.
- **NFC/NFD** xử lý canonical equivalence; **NFKC/NFKD** xử lý cả compatibility equivalence và có thể gộp các biểu diễn mà sản phẩm cần phân biệt.
- **Chuẩn hóa phải có chính sách theo dữ liệu**: văn bản hiển thị, search key, identifier, mật khẩu và tài liệu cần bảo tồn không nhất thiết dùng cùng form.
- **NFC không phải loại bỏ dấu**, **NFKC không phải phát hiện mọi confusables**, và Unicode normalization không thay thế collation, case folding, validation hay escaping.
- Kiểm tra **hai phía của phép so sánh**, giữ nhất quán giữa lưu trữ/index/truy vấn và cân nhắc Unicode version/JDK khi thay đổi policy.
- Với hệ thống bản địa hóa, ưu tiên bảo tồn ý nghĩa văn bản và cung cấp các dạng chuẩn hóa dẫn xuất đúng mục tiêu, thay vì sửa âm thầm mọi Unicode đầu vào.
