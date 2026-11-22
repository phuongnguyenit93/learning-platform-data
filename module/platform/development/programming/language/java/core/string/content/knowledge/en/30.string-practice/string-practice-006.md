# So sánh tên tiếng Việt sau chuẩn hóa phù hợp trong Java

## 1. Bài toán: tên trông giống nhau nhưng `String.equals()` trả về `false`

Tên tiếng Việt chứa các chữ có dấu như **Hòa**, **Thảo**, **Nguyễn**, **Đỗ**. Trong Unicode, một chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cơ sở kèm các **combining mark** (dấu kết hợp). Hai cách viết có thể hiển thị giống nhau nhưng chứa các code point khác nhau.

Ví dụ, `"Hòa"` và `"Ho\u0300a"` thường trông như nhau:

~~~java
String composed = "H\u00F2a";     // Hòa: chữ ò đã dựng sẵn
String decomposed = "Ho\u0300a"; // Ho + combining grave + a

System.out.println(composed.equals(decomposed)); // false
~~~

`String.equals()` so sánh **dãy UTF-16 code unit**, nên trả về `false` khi hai biểu diễn khác nhau. Điều này có thể làm tìm kiếm, phát hiện tên trùng hoặc kiểm thử chuỗi thất bại dù người dùng nhìn thấy cùng một tên.

**Cách giải quyết cho trường hợp tương đương Unicode theo chuẩn:** chuyển cả hai chuỗi về cùng một **Unicode normalization form**, thường là **NFC**, rồi so sánh bằng `equals()`:

~~~java
import java.text.Normalizer;

String left = Normalizer.normalize("H\u00F2a", Normalizer.Form.NFC);
String right = Normalizer.normalize("Ho\u0300a", Normalizer.Form.NFC);

System.out.println(left.equals(right)); // true
~~~

Tuy nhiên, **chuẩn hóa Unicode không đồng nghĩa bỏ dấu, bỏ phân biệt hoa/thường hoặc khẳng định hai con người là một**. Cần xác định quy tắc so sánh dựa trên mục đích nghiệp vụ trước khi viết API.

## 2. Các cấp độ “bằng nhau” của tên

| Mục đích | Ví dụ | Quy tắc phù hợp |
| --- | --- | --- |
| So sánh chính xác nội dung chuỗi | `"Hòa"` với chính `"Hòa"` | `String.equals()` |
| Coi hai biểu diễn Unicode tương đương là cùng chữ | `"Hòa"` và `"Ho\u0300a"` | Chuẩn hóa **NFC** cả hai rồi `equals()` |
| Bỏ qua hoa/thường để tìm kiếm | `"HÒA"` và `"hòa"` | Quy tắc case được thống nhất, rồi chuẩn hóa |
| Bỏ qua khoảng trắng thừa theo chính sách ứng dụng | `" Hòa  "` và `"Hòa"` | Chuẩn hóa khoảng trắng **nếu nghiệp vụ cho phép** |
| Sắp xếp tên theo ngôn ngữ | `"Hoa"`, `"Hòa"`, `"Đỗ"` | `Collator` theo locale tiếng Việt với cấu hình rõ ràng |
| Tìm gần đúng, chấp nhận thiếu dấu | `"Hoa"` và `"Hòa"` | Chiến lược tìm kiếm gần đúng hoặc accent-insensitive riêng |
| Xác định **cùng một người** | Hai hồ sơ cùng tên | Cần mã định danh và dữ liệu xác minh; tên không đủ |

Chẳng hạn, `"Hoa"` và `"Hòa"` là **hai chuỗi khác nhau** ngay cả sau NFC. Tự động bỏ tất cả dấu tiếng Việt có thể làm gộp các tên hợp lệ khác nhau. Tương tự, chữ **`đ`** và **`d`** không phải cùng một ký tự; NFC không biến ký tự này thành ký tự kia.

Với tên người, nên phân biệt rõ:

1. **Tên hiển thị:** giữ chính tả và cách viết người dùng cung cấp, có thể lưu kèm dạng Unicode thống nhất.
2. **Khóa so sánh:** giá trị được tạo bằng chính sách đã công bố, phục vụ tìm kiếm hoặc loại trùng theo quy ước.
3. **Định danh hồ sơ:** dùng ID duy nhất, không dùng tên đã chuẩn hóa để quyết định hai bản ghi thuộc cùng một người.

## 3. Unicode normalization: NFC, NFD, NFKC và NFKD

Java cung cấp `java.text.Normalizer` với bốn dạng:

| Dạng | Ý nghĩa chính | Cân nhắc khi xử lý tên |
| --- | --- | --- |
| **NFC** | Phân rã chuẩn tắc rồi ghép lại theo dạng tổ hợp chuẩn | Lựa chọn thực dụng cho so sánh tương đương Unicode của tên |
| **NFD** | Phân rã chuẩn tắc | Có thể dùng trước một số bước xử lý dấu, nhưng chưa có nghĩa là bỏ dấu |
| **NFKC** | Chuẩn hóa **compatibility** rồi tổ hợp | Có thể biến đổi thêm các ký tự tương thích; cần chính sách nghiệp vụ |
| **NFKD** | Phân rã **compatibility** | Tăng phạm vi biến đổi so với NFD; không tự động phù hợp với tên riêng |

Hai chuỗi **canonically equivalent** sẽ bằng nhau sau NFC hoặc NFD. Việc gọi NFC nhiều lần trên cùng một chuỗi đã chuẩn hóa không làm đổi kết quả (**idempotent**).

~~~java
String input = "Ho\u0300a";
String nfc = Normalizer.normalize(input, Normalizer.Form.NFC);

System.out.println(nfc.equals("H\u00F2a")); // true
System.out.println(Normalizer.isNormalized(
        nfc, Normalizer.Form.NFC));          // true
~~~

**Không mặc định dùng NFKC cho mọi tên người.** Chuẩn hóa compatibility có thể làm mất khác biệt kiểu chữ hoặc biểu diễn mà hệ thống muốn giữ nguyên. Nếu cần loại trùng theo một chuẩn cụ thể, tài liệu hệ thống phải ghi rõ **dạng chuẩn hóa** và giai đoạn áp dụng.

Cũng không thể suy ra hai chuỗi “bằng nhau” chỉ vì chúng hiển thị gần giống. Ký tự thuộc bảng chữ cái khác, ký tự vô hình hay cách ghép emoji có thể tạo văn bản nhìn tương tự mà không canonically equivalent.

## 4. Thiết kế chính sách chuẩn hóa tên tiếng Việt

Một chính sách tối thiểu thường phù hợp cho **so sánh tên đầy đủ chính xác nhưng chấp nhận khác biệt biểu diễn Unicode** là:

- Quyết định rõ có cho phép bỏ khoảng trắng ở đầu/cuối và gộp nhiều khoảng trắng liên tiếp hay không.
- Chuyển về **NFC**.
- Giữ nguyên **dấu tiếng Việt**, chữ `đ`, chữ hoa/thường và các chữ cái khác, trừ khi nghiệp vụ yêu cầu khác.
- So sánh hai kết quả với `equals()`.

Ví dụ riêng: khi sản phẩm cho phép gộp mọi cụm whitespace theo chính sách nhập liệu, kể cả một số ký tự khoảng trắng Unicode, có thể chuẩn hóa bằng:

~~~java
String collapsed = input.replaceAll("[\\p{Z}\\s]+", " ").strip();
String normalized = Normalizer.normalize(
        collapsed, Normalizer.Form.NFC);
~~~

Trong regex Java, `\p{Z}` là nhóm Unicode separator; `\s` (trong chế độ mặc định) bao phủ các whitespace phổ biến như dấu cách, tab và xuống dòng. Hai lớp được phối hợp ở đây nhằm chuyển các khoảng phân cách tương ứng thành **một dấu cách ASCII**, rồi `strip()` bỏ dấu cách đầu/cuối.

**Đây là một quyết định ứng dụng**, không phải chức năng bắt buộc của NFC. Nó có thể làm thay đổi tên chứa khoảng trắng đặc biệt hoặc xuống dòng. Trong dữ liệu pháp lý, tên hiển thị hoặc tài liệu cần lưu nguyên văn, chỉ nên tạo **khóa phụ** đã chuẩn hóa và vẫn bảo toàn dữ liệu gốc.

### Tìm kiếm không phân biệt hoa/thường

Nếu yêu cầu là tìm `"HÒA"` bằng `"hòa"`, có thể tạo khóa tìm kiếm bằng chữ thường:

~~~java
import java.util.Locale;

String searchKey = Normalizer.normalize(
        normalized.toLowerCase(Locale.ROOT),
        Normalizer.Form.NFC);
~~~

`Locale.ROOT` giúp tránh phụ thuộc vào default locale của máy chạy khi quy tắc nghiệp vụ là **khóa tìm kiếm kỹ thuật ổn định**. Tuy nhiên, lowercase không phải Unicode **full case folding** và không thay thế toàn bộ quy tắc so sánh văn bản theo ngôn ngữ. Nếu sản phẩm cần case-insensitive matching đa ngôn ngữ với yêu cầu nghiêm ngặt, phải chọn và kiểm thử thuật toán theo đặc tả đó.

Không nên hạ chữ thường hoặc bỏ dấu trên **bản tên hiển thị** chỉ để tìm kiếm. Giữ nguyên tên gốc và tạo search key riêng.

## 5. Ví dụ Java 17+ hoàn chỉnh: so sánh, tìm kiếm và loại trùng theo chính sách

Lưu vào file `VietnameseNameComparisonDemo.java`:

~~~java
import java.text.Collator;
import java.text.Normalizer;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class VietnameseNameComparisonDemo {
    // Chính sách ví dụ: gom whitespace, bỏ khoảng trắng biên, chuẩn hóa NFC.
    static String canonicalName(String input) {
        Objects.requireNonNull(input, "input");
        String spaced = input.replaceAll("[\\p{Z}\\s]+", " ").strip();
        return Normalizer.normalize(spaced, Normalizer.Form.NFC);
    }

    // Khóa tìm kiếm chấp nhận khác biệt hoa/thường nhưng giữ dấu.
    static String searchKey(String input) {
        String lowered = canonicalName(input).toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lowered, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String composed = "H\u00F2a";      // Hòa
        String decomposed = "Ho\u0300a";  // Ho + dấu huyền + a
        String withSpaces = "  H\u00F2a\u00A0  ";

        System.out.println("rawEquals=" +
                composed.equals(decomposed));
        System.out.println("nfcEquals=" +
                canonicalName(composed).equals(canonicalName(decomposed)));
        System.out.println("spacesEquals=" +
                canonicalName(withSpaces).equals(canonicalName(composed)));
        System.out.println("caseSearchEquals=" +
                searchKey("H\u00D2A").equals(searchKey(decomposed)));
        System.out.println("accentPreserved=" +
                !searchKey("Hoa").equals(searchKey(composed)));

        Set<String> exactKeys = new HashSet<>();
        for (String name : List.of(
                composed, decomposed, withSpaces, "Hoa")) {
            exactKeys.add(canonicalName(name));
        }
        System.out.println("exactKeyCount=" + exactKeys.size());

        Set<String> searchKeys = new HashSet<>();
        for (String name : List.of(
                composed, "h\u00F2a", "H\u00D2A", "Hoa")) {
            searchKeys.add(searchKey(name));
        }
        System.out.println("searchKeyCount=" + searchKeys.size());

        Collator vi = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
        vi.setStrength(Collator.TERTIARY);

        System.out.println("collatorCanonical=" +
                (vi.compare(composed, decomposed) == 0));
        System.out.println("nfcIdempotent=" +
                canonicalName(decomposed)
                        .equals(canonicalName(canonicalName(decomposed))));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 VietnameseNameComparisonDemo.java
java VietnameseNameComparisonDemo
~~~

`stdout` kỳ vọng trên JDK Java 17+ hỗ trợ locale tiếng Việt:

~~~text
rawEquals=false
nfcEquals=true
spacesEquals=true
caseSearchEquals=true
accentPreserved=true
exactKeyCount=2
searchKeyCount=2
collatorCanonical=true
nfcIdempotent=true
~~~

**Giải thích theo thứ tự:**

1. Hai biểu diễn `Hòa` khác nhau ở cấp độ code unit nên `rawEquals=false`.
2. NFC đưa chúng về dạng tương đương nên `nfcEquals=true`.
3. Chính sách gom separator và bỏ khoảng trắng biên làm cho tên có NBSP (`\u00A0`) khớp tên chuẩn, nên `spacesEquals=true`.
4. Hạ chữ thường để tạo search key cho phép `HÒA` khớp `Hòa`, nhưng **không bỏ dấu**, nên `Hoa` vẫn khác `Hòa`.
5. Tập `exactKeys` và `searchKeys` đều còn hai khóa: nhóm tên `Hòa` và tên `Hoa`.
6. `Collator` với decomposition chuẩn tắc nhận thấy hai biểu diễn canonically equivalent của cùng chữ là bằng nhau.
7. NFC áp dụng lặp lại không làm đổi giá trị.

Đây là ví dụ **chính sách so sánh được chọn**, không phải hàm duy nhất “đúng” cho mọi nghiệp vụ. Nếu hệ thống cần giữ tất cả khoảng trắng gốc hoặc phân biệt chính xác chữ hoa/thường, cần điều chỉnh bước tạo khóa và cập nhật test tương ứng.

## 6. `Collator`: khi cần so sánh tên theo tiếng Việt để sắp xếp

`String.compareTo()` so sánh thứ tự code unit UTF-16; nó **không** phải bộ sắp xếp tên theo quy tắc ngôn ngữ tiếng Việt. Khi hiển thị danh sách tên theo bảng chữ cái, dùng `java.text.Collator` với locale phù hợp:

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

Collator vi = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
vi.setStrength(Collator.TERTIARY);

List<String> names = new ArrayList<>(
        List.of("Đỗ", "Hoa", "Hòa", "An"));

names.sort(vi);
~~~

Đoạn này minh họa code **bên trong một phương thức**. `Collator` có thể được dùng làm `Comparator<String>` cho sắp xếp. Không nên khẳng định cứng một thứ tự tên cụ thể áp dụng trên mọi bản JDK hoặc provider: kết quả collation có thể thay đổi theo dữ liệu locale và implementation.

### Strength, decomposition và tác động tới phép so sánh

`Collator` có các mức `PRIMARY`, `SECONDARY`, `TERTIARY` và `IDENTICAL`. Mức càng thấp thì càng có thể bỏ qua một số khác biệt khi so sánh; mức cao hơn xét nhiều chi tiết hơn. Cụ thể **dấu và chữ hoa/thường được coi là khác nhau ở mức nào** phụ thuộc bộ quy tắc collation của locale được dùng.

Đối với tên tiếng Việt:

- Nếu cần giữ sự khác biệt về dấu, **đừng tự giả định** rằng `PRIMARY` sẽ phù hợp; cần kiểm thử tập tên thực tế, gồm cả `d`/`đ` và các dấu thanh.
- Nếu muốn phép so sánh cân nhắc các chi tiết chữ viết, `TERTIARY` là lựa chọn ban đầu có thể thử nghiệm, sau đó đánh giá yêu cầu nghiệp vụ.
- `CANONICAL_DECOMPOSITION` hỗ trợ so sánh những biểu diễn Unicode tương đương chuẩn tắc; việc NFC trước khi đưa vào bộ sắp xếp cũng làm dữ liệu nhất quán hơn.
- `Collator` có trạng thái cấu hình và không nên chia sẻ một instance mutable không đồng bộ giữa nhiều thread; tạo hoặc quản lý instance theo vòng đời phù hợp.

**Quan trọng với collection:** `TreeSet` và `TreeMap` dùng `compare(a,b) == 0` để xác định hai khóa được coi là tương đương. Trong khi đó, `HashSet` và `HashMap` dựa trên `equals/hashCode`. Khi comparator có quy tắc khác `String.equals`, hai loại collection có thể quyết định trùng lặp khác nhau. Chọn comparator để **sắp xếp** không đồng nghĩa được phép dùng nó làm bằng chứng rằng hai hồ sơ là cùng một người.

## 7. Có nên bỏ dấu khi tìm tên?

Một ô tìm kiếm có thể muốn người dùng gõ `Hoa` vẫn thấy `Hòa`; đó là **tìm kiếm gần đúng/không phân biệt dấu**, không phải tương đương chuẩn tắc NFC. Cần đặt tên và công bố chính sách riêng.

Cách “phân rã NFD rồi xóa tất cả combining mark” có thể làm mất thông tin tiếng Việt, tạo trùng tên không mong muốn; riêng chữ **`đ`** không tự biến thành `d` chỉ qua NFD. Nếu nghiệp vụ thực sự cần tìm không dấu:

1. Giữ **dữ liệu tên gốc** và **khóa NFC** để so sánh chính xác.
2. Tạo **chỉ mục tìm kiếm phụ** theo chính sách bỏ dấu được tài liệu hóa; cân nhắc cách xử lý `đ`/`d`.
3. Dùng chỉ mục phụ để đưa ra **kết quả gợi ý**, sau đó hiển thị tên chính xác để người dùng xác nhận.
4. Tránh dùng khóa bỏ dấu làm primary key hoặc căn cứ duy nhất để gộp hồ sơ.

Không có quy tắc “bỏ dấu tiếng Việt” duy nhất phù hợp đồng thời cho tìm kiếm, phân tích ngôn ngữ, pháp lý và định danh người dùng.

## 8. Lưu dữ liệu gốc, khóa chuẩn hóa và định danh riêng

Một thiết kế dữ liệu thực tế có thể lưu:

| Trường | Ví dụ | Công dụng |
| --- | --- | --- |
| `person_id` | `8742` | Định danh duy nhất, ổn định của hồ sơ |
| `display_name` | `Hòa` | Văn bản hiển thị theo lựa chọn người dùng |
| `canonical_name` | `Hòa` ở NFC | So sánh tương đương Unicode và khoảng trắng theo chính sách |
| `search_name_key` | `hòa` | Tìm kiếm không phân biệt hoa/thường nhưng giữ dấu |
| `accent_insensitive_key` (nếu cần) | Giá trị theo thuật toán tìm gần đúng đã duyệt | Tìm kiếm phụ, không định danh |

Tên người **không phải khóa duy nhất đáng tin cậy**. Hai người khác nhau có thể trùng họ tên, còn một người có thể thay đổi tên hoặc cách nhập. Dù khóa chuẩn hóa trùng, hành động gộp hồ sơ thường cần thêm ID, thuộc tính nghiệp vụ và bước xác nhận tương ứng.

Cũng cần thống nhất quy tắc giữa frontend, backend và cơ sở dữ liệu. SQL collation có thể có quy tắc tương đương khác với `Normalizer` và `Collator` của Java. Nếu có unique constraint trên một trường tên, hãy kiểm thử rằng cơ chế so sánh tại database thực hiện đúng điều ứng dụng kỳ vọng.

## 9. Những lỗi thường gặp

| Sai lầm | Tác hại | Cách xử lý |
| --- | --- | --- |
| Dùng `equals()` trực tiếp với hai biểu diễn NFC/NFD khác nhau | Tên trông giống nhau nhưng không khớp | Chuẩn hóa cùng NFC trước khi so sánh |
| Nghĩ NFC tự bỏ dấu | Gộp sai chính sách so sánh | Phân biệt canonical equivalence với accent-insensitive search |
| Biến `Hòa` thành `Hoa` rồi coi là cùng người | Mất sự khác biệt tên hợp lệ | Giữ dấu cho so sánh chính xác; bỏ dấu chỉ cho tìm kiếm được thiết kế riêng |
| Cho rằng `đ` và `d` tương đương do NFD | Hiểu sai normalization | Kiểm tra quy tắc riêng nếu cần bỏ dấu |
| Chỉ chuyển chữ thường ở một phía | Kết quả phụ thuộc nguồn dữ liệu | Áp dụng cùng thuật toán tạo khóa ở cả lúc lưu và tra |
| Dùng `toLowerCase()` không chỉ định locale | Có thể phụ thuộc default locale | Chọn locale rõ ràng theo mục đích |
| Dùng `Collator` mà không cố định locale/strength | Khó tái hiện hành vi qua môi trường | Cấu hình và kiểm thử locale, strength, decomposition |
| Dùng `TreeSet` để loại trùng hồ sơ | Comparator có thể coi tên khác nhau là trùng | Dùng ID và chính sách trùng lặp nghiệp vụ |
| Ghi đè tên gốc bằng search key | Mất chính tả, dấu, cách viết hiển thị | Lưu `display_name` riêng |
| Tin vào tên đã chuẩn hóa như một định danh | Có thể gộp hai người khác nhau | Dùng ID ổn định và dữ liệu xác minh bổ sung |

### Tình huống Unicode cần test

- `"Hòa"` dựng sẵn và `"Ho\u0300a"` tổ hợp dấu.
- `"HÒA"`, `"Hòa"` và `"hòa"` khi tìm kiếm không phân biệt hoa/thường.
- `"Hoa"` so với `"Hòa"` khi chính sách **giữ dấu**.
- `"Đỗ"` so với `"Dỗ"`: không được tự đồng nhất chữ `đ` và `d`.
- Tên có khoảng trắng đầu/cuối, nhiều dấu cách hoặc NBSP.
- Tên có combining mark đặt ở thứ tự hợp lệ nhưng biểu diễn khác nhau.
- Ký tự vô hình, dấu câu và dấu gạch nối trong tên; không tự xóa nếu chưa có quy tắc.
- Các bộ dữ liệu tên thực tế được sắp xếp bởi `Collator` với phiên bản JDK và provider dự kiến.
- Giá trị `null`, chuỗi rỗng và tên chỉ chứa whitespace; phải quyết định rõ chấp nhận hay từ chối.

## 10. Checklist thiết kế và triển khai

1. Xác định đây là **so sánh hiển thị chính xác**, **tìm kiếm**, **sắp xếp** hay **định danh con người**.
2. Chọn dạng chuẩn hóa Unicode (thông thường NFC) và cách xử lý whitespace theo chính sách.
3. Quyết định có phân biệt hoa/thường, dấu tiếng Việt và `đ`/`d` hay không; không ngầm coi chúng tương đương.
4. Viết một hàm tạo khóa, dùng thống nhất ở phía lưu và phía tìm kiếm.
5. Giữ tên hiển thị gốc, lưu khóa phụ nếu cần, dùng ID để quản lý hồ sơ.
6. Với việc sắp xếp, cấu hình locale và strength cho `Collator`, tránh giả định rằng thứ tự không bao giờ đổi giữa các môi trường.
7. Đồng bộ quy tắc ứng dụng với database collation, unique index và chức năng tìm kiếm.
8. Kiểm thử các chuỗi cùng hình thức hiển thị nhưng khác dãy code point, cũng như những tên **thực sự khác nhau** chỉ bởi dấu.

**Kết luận:** Để so sánh tên tiếng Việt hợp lý, hãy dùng **NFC** nhằm giải quyết khác biệt biểu diễn Unicode, và viết rõ các bước xử lý khoảng trắng, chữ hoa/thường hoặc tìm kiếm không dấu theo yêu cầu thực tế. `String.equals()` sau chuẩn hóa phù hợp cho khóa so sánh nội dung; `Collator` hỗ trợ sắp xếp theo ngôn ngữ; còn nhận diện **cùng một người** phải dựa vào định danh và quy tắc nghiệp vụ, không dựa duy nhất vào tên.
