# Normalizer và những dạng biểu diễn cùng nội dung Unicode trong Java

> **Phạm vi:** Java 15 và những kiến thức còn áp dụng trên các JDK hiện đại. API `java.text.Normalizer` và bốn dạng chuẩn hóa Unicode là những cơ chế ổn định, không phải tính năng preview. Bài học phân biệt **các chuỗi nhìn giống nhau**, **chuỗi tương đương theo Unicode** và **chuỗi giống hệt nhau về mã ký tự**; sau đó áp dụng vào so sánh, lưu trữ, tra cứu và xử lý tiếng Việt.

## 1. Cùng nhìn thấy một chữ nhưng máy có thể lưu khác nhau

Ký tự **é** có thể được biểu diễn ít nhất theo hai cách:

- **Dạng dựng sẵn (precomposed):** một code point **U+00E9**, tên Unicode `LATIN SMALL LETTER E WITH ACUTE`.
- **Dạng tách rời (decomposed):** code point **U+0065** (`e`) theo sau bởi **U+0301** (`COMBINING ACUTE ACCENT`).

Hai biểu diễn này thường được hiển thị giống nhau. Với người đọc, chúng có cùng nội dung chữ có dấu; nhưng với chương trình Java, dãy đơn vị mã UTF-16 của chúng **khác nhau**.

~~~java
// Đoạn minh họa bên trong phương thức:
String composed = "caf\u00E9";    // c a f é
String decomposed = "cafe\u0301"; // c a f e + dấu sắc kết hợp

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length());           // 4
System.out.println(decomposed.length());         // 5
~~~

`String.equals` so sánh **chuỗi ký tự chính xác** theo các đơn vị mã tương ứng, nên trả về `false`. `String.length()` đếm **UTF-16 code units**, không đo số “chữ mà con người nhìn thấy”. Vì tất cả các code point trong ví dụ thuộc Basic Multilingual Plane (BMP), số code units ở đây lần lượt là 4 và 5.

Vấn đề này thường xuất hiện khi:

- Văn bản được gõ qua bộ gõ/IME khác nhau, sao chép từ tài liệu, trình duyệt hoặc thiết bị khác nhau.
- Dữ liệu được import, đồng bộ hoặc di chuyển giữa các hệ thống.
- Ứng dụng dùng chuỗi làm **khóa `Map`**, điều kiện `equals`, tiêu chí trùng lặp, khóa database hoặc bộ lọc tìm kiếm.
- Văn bản tiếng Việt có chữ ghép dấu: nhìn cùng từ nhưng dữ liệu lưu một hoặc nhiều code point.

**Mục tiêu của normalization:** đưa các cách biểu diễn được **Unicode xác định là tương đương** về một dạng quy chuẩn để so sánh/lưu trữ đáng tin cậy hơn. Nó **không** có nghĩa “mọi thứ nhìn giống nhau sẽ trở thành giống nhau”.

## 2. Phân biệt code point, UTF-16 code unit và ký tự hiển thị

Trước khi dùng `Normalizer`, cần phân biệt ba mức:

| Mức | Ý nghĩa | API/kiểm tra |
| --- | --- | --- |
| **Unicode code point** | Một giá trị Unicode, ví dụ `U+00E9` hay `U+0301` | `String.codePoints()`, `codePointAt(...)`, `codePointCount(...)` |
| **UTF-16 code unit** | Đơn vị lưu trữ 16-bit được `String`/`char` thể hiện; một code point ngoài BMP dùng **hai** code units (surrogate pair) | `String.length()`, `charAt(...)` |
| **Grapheme cluster / ký tự người dùng cảm nhận** | Một đơn vị hiển thị có thể gồm nhiều code point, ví dụ chữ cái và dấu kết hợp, hoặc chuỗi emoji | Cần quy tắc phân đoạn Unicode phù hợp; `length()` và `codePointCount()` không trực tiếp đếm số “chữ hiển thị” |

Ví dụ với `e` + dấu sắc kết hợp:

~~~text
U+0065  LATIN SMALL LETTER E
U+0301  COMBINING ACUTE ACCENT
          |
          v
     Hiển thị gần như "é"
~~~

Trong ví dụ này, **hai code points** có thể cùng tạo ra **một ký tự người dùng cảm nhận**. Do đó:

~~~java
String s = "e\u0301";
System.out.println(s.length()); // 2
System.out.println(s.codePointCount(0, s.length())); // 2
~~~

Kết quả cả hai đều là `2` trong trường hợp này, nhưng người dùng có thể nhìn như một chữ `é`. Đếm code point và normalization giải quyết **hai bài toán khác nhau**: normalization chuẩn hóa cách biểu diễn tương đương, còn đếm/grapheme segmentation xử lý đơn vị văn bản.

## 3. Hai quan hệ tương đương Unicode cần biết

### 3.1. Canonical equivalence — tương đương chính tắc

Unicode quy định một số dãy code point khác nhau có **cùng biểu diễn trừu tượng về ký tự**. Ví dụ `U+00E9` và `U+0065 U+0301` là **canonically equivalent**.

Với hai chuỗi canonically equivalent, chuẩn hóa về **NFC** hoặc **NFD** sẽ cho chuỗi tương ứng **giống hệt nhau để so sánh chính xác**.

Điều này quan trọng vì hình thức hiển thị không đủ để xác nhận dữ liệu bằng nhau, trong khi quan hệ canonical equivalence là quy tắc rõ ràng của Unicode.

### 3.2. Compatibility equivalence — tương đương tương thích

Một số ký tự Unicode tồn tại để biểu diễn kiểu trình bày, kiểu chữ, vị trí hoặc tương thích dữ liệu. Unicode cho phép quy đổi một số khác biệt này trong chuẩn hóa **compatibility**.

Ví dụ:

- Ký tự **①** (U+2460, circled digit one) có compatibility mapping sang chữ số **1**.
- Ký tự ligature **ﬁ** (U+FB01) có compatibility mapping sang hai chữ **fi**.
- Một số ký tự chữ/số *fullwidth* có compatibility mapping về các ký tự ASCII tương ứng.

Khác với canonical equivalence, compatibility normalization **có thể làm mất một khác biệt mà người dùng hoặc nghiệp vụ coi là có ý nghĩa**. Nếu văn bản là một biểu thức toán, biểu tượng kỹ thuật, nội dung nghệ thuật hoặc dữ liệu cần lưu nguyên trạng, đừng tự động quy đổi toàn bộ thành compatibility form.

**Lưu ý:** hai ký tự trông giống nhau không tự nhiên trở thành tương đương canonical hay compatibility. Chẳng hạn chữ Latin `a` và một chữ ở bảng chữ khác trông gần giống `a` có thể vẫn là hai code point khác biệt sau normalization. Quy tắc chống giả mạo/homoglyph phải được xử lý riêng.

## 4. Bốn dạng Unicode Normalization Form

Unicode Standard Annex #15 định nghĩa bốn dạng. Java cung cấp chúng trong enum `java.text.Normalizer.Form`:

| Form | Tên đầy đủ / cơ chế | Mục đích và hệ quả |
| --- | --- | --- |
| **NFD** | **N**ormalization **F**orm **D**; canonical **decomposition** (phân rã chính tắc và sắp thứ tự dấu kết hợp theo quy tắc) | Đưa các ký tự có decomposition chính tắc về dãy thành phần; hữu ích cho xử lý thành phần ký tự |
| **NFC** | **N**ormalization **F**orm **C**; canonical decomposition rồi **composition** khi được phép | Thường phù hợp làm dạng chuẩn cho văn bản thông thường; các biểu diễn canonically equivalent cùng trở về một kết quả |
| **NFKD** | **N**ormalization **F**orm **K**ompatibility **D**; compatibility decomposition | Tách cả những ký tự có compatibility mappings; có thể xóa khác biệt biểu diễn |
| **NFKC** | **N**ormalization **F**orm **K**ompatibility **C**; compatibility decomposition rồi canonical composition | Hữu ích cho một số chính sách so khớp identifier/đầu vào hạn chế, **nhưng cần định nghĩa rõ phạm vi vì có mất mát thông tin** |

Cách đọc tên: `D` = **decomposed**, `C` = **composed**; chữ `K` đánh dấu **compatibility**. Cả bốn form đều chuẩn hóa thứ tự các combining mark theo các quy tắc Unicode, không đơn thuần thay một chữ bằng hai chữ.

Ví dụ:

| Dữ liệu ban đầu | NFC | NFD | NFKC | NFKD |
| --- | --- | --- | --- | --- |
| `U+00E9` (é dựng sẵn) | `U+00E9` | `U+0065 U+0301` | `U+00E9` | `U+0065 U+0301` |
| `U+0065 U+0301` (e + dấu sắc) | `U+00E9` | `U+0065 U+0301` | `U+00E9` | `U+0065 U+0301` |
| `U+2460` (①) | Vẫn là `U+2460` | Vẫn là `U+2460` | `U+0031` (`1`) | `U+0031` (`1`) |
| `U+FB01` (ﬁ) | Vẫn là `U+FB01` | Vẫn là `U+FB01` | `U+0066 U+0069` (`fi`) | `U+0066 U+0069` (`fi`) |

Không suy diễn rằng **NFC luôn tạo ra một code point duy nhất**, hoặc NFD luôn khiến chuỗi dài hơn. Chỉ những tổ hợp đủ điều kiện mới được ghép lại; nhiều ký tự Unicode không có dạng dựng sẵn để ghép, và một số chuỗi có dấu vẫn gồm nhiều code point sau NFC.

## 5. API Java chính thức: `java.text.Normalizer`

Hai thao tác cốt lõi:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        input,
        Normalizer.Form.NFC
);

boolean alreadyNormalized = Normalizer.isNormalized(
        input,
        Normalizer.Form.NFC
);
~~~

Đây là **mảnh mã nằm bên trong một phương thức**, giả định có `String input`. Hai phương thức cần biết:

- `Normalizer.normalize(CharSequence src, Normalizer.Form form)` trả về một `String` được chuẩn hóa theo form đã chọn.
- `Normalizer.isNormalized(CharSequence src, Normalizer.Form form)` kiểm tra dữ liệu đã ở dạng form mong muốn chưa.

Không có bước “bật chế độ chuẩn hóa toàn JVM”. `String`, `equals`, `HashMap`, `Files.readString`, JDBC và nhiều API khác **không tự động gọi `Normalizer.normalize`** cho từng dữ liệu ứng dụng. Lập trình viên phải xác định **thời điểm và chính sách** chuẩn hóa.

Đây là API Java SE ổn định trong module `java.base`, không cần thêm thư viện ngoài, không cần `--enable-preview`. Nó đã tồn tại từ trước Java 15 và vẫn tiếp tục dùng trong các JDK hiện đại.

### Chọn NFC mặc định cho dữ liệu văn bản thông thường khi có nhu cầu chuẩn hóa

Với trường văn bản tự do mà nghiệp vụ coi canonical-equivalent strings là cùng một giá trị, **NFC** thường là lựa chọn thực tế. Điều này bảo toàn các phân biệt về compatibility mà NFKC có thể xóa.

Nếu muốn biến cả các kiểu chữ tương thích thành một khóa tìm kiếm, **NFKC** có thể là một bước trong một **chính sách matching riêng**, nhưng cần kiểm tra điều gì sẽ bị gộp. Không mặc định lưu đè nguyên bản bằng NFKC.

## 6. Chương trình Java đầy đủ: chứng minh hai cách biểu diễn cùng nội dung

Lưu toàn bộ mã sau thành file **`NormalizerDemo.java`**:

~~~java
import java.text.Normalizer;

public class NormalizerDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: " + composed.equals(decomposed));
        System.out.println("Raw lengths: "
                + composed.length() + " / " + decomposed.length());

        String a = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String b = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: " + a.equals(b));
        System.out.println("NFC lengths: "
                + a.length() + " / " + b.length());
        System.out.println("NFD lengths: "
                + Normalizer.normalize(
                        composed, Normalizer.Form.NFD).length()
                + " / "
                + Normalizer.normalize(
                        decomposed, Normalizer.Form.NFD).length());

        System.out.println("Decomposed already NFC: "
                + Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFC));
        System.out.println("Decomposed already NFD: "
                + Normalizer.isNormalized(
                        decomposed, Normalizer.Form.NFD));

        String circledOne = "\u2460";
        System.out.println("NFC keeps circled 1: "
                + Normalizer.normalize(
                        circledOne, Normalizer.Form.NFC)
                        .equals(circledOne));
        System.out.println("NFKC becomes digit 1: "
                + Normalizer.normalize(
                        circledOne, Normalizer.Form.NFKC)
                        .equals("1"));

        String vietnameseComposed = "\u1EAF";
        String vietnameseDecomposed = "a\u0306\u0301";
        System.out.println("Vietnamese raw equals: "
                + vietnameseComposed.equals(vietnameseDecomposed));
        System.out.println("Vietnamese NFC equals: "
                + Normalizer.normalize(
                        vietnameseComposed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                        vietnameseDecomposed, Normalizer.Form.NFC)));

        System.out.println("NFC idempotent: "
                + Normalizer.normalize(a, Normalizer.Form.NFC)
                        .equals(a));
        System.out.println("NFC does not remove accent: "
                + !Normalizer.normalize(
                        "a", Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                        "\u00E1", Normalizer.Form.NFC)));
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac NormalizerDemo.java
java NormalizerDemo
~~~

**Stdout chính xác:**

~~~text
Raw equals: false
Raw lengths: 4 / 5
NFC equals: true
NFC lengths: 4 / 4
NFD lengths: 5 / 5
Decomposed already NFC: false
Decomposed already NFD: true
NFC keeps circled 1: true
NFKC becomes digit 1: true
Vietnamese raw equals: false
Vietnamese NFC equals: true
NFC idempotent: true
NFC does not remove accent: true
~~~

Giải thích:

1. `String.equals` ban đầu là `false` vì hai `String` có dãy code units khác nhau.
2. **NFC** biến `e + U+0301` thành `U+00E9`; cả hai chuỗi thành bốn code units.
3. **NFD** phân rã `U+00E9` thành `e + U+0301`; cả hai chuỗi thành năm code units.
4. `isNormalized` chỉ kiểm tra xem chuỗi đã đúng **form được yêu cầu** hay chưa, không trả lời “đây có phải chuỗi Unicode hợp lệ về mặt nội dung/ngữ nghĩa?”.
5. Ký tự **①** được NFC giữ nguyên nhưng NFKC quy về chữ số **1**.
6. Chữ **ắ** (U+1EAF) và dãy `a + U+0306 (breve) + U+0301 (acute)` cũng trở thành bằng nhau sau NFC. Đây là ví dụ thực tế với tiếng Việt.
7. Chuẩn hóa **idempotent**: chuẩn hóa lần nữa với **cùng form** không làm thay đổi kết quả đã chuẩn hóa.
8. NFC **không xóa dấu tiếng Việt**: `a` và `á` vẫn là hai chữ khác nhau.

Có thể kiểm tra source API ở mức Java 15 nếu trình biên dịch hiện tại còn hỗ trợ target đó:

~~~bash
javac --release 15 NormalizerDemo.java
~~~

Đây là mã dùng API chính thức, không phụ thuộc preview hoặc API nội bộ.

## 7. Tiếng Việt: cùng chữ có dấu nhưng có thể được mã hóa khác nhau

Tiếng Việt thường kết hợp **chữ cơ sở**, dấu phụ biểu diễn nguyên âm và dấu thanh. Ví dụ chữ **ắ** có thể có hai cách biểu diễn:

~~~text
Dạng dựng sẵn:
  U+1EAF           LATIN SMALL LETTER A WITH BREVE AND ACUTE

Dạng phân rã:
  U+0061           LATIN SMALL LETTER A
  U+0306           COMBINING BREVE
  U+0301           COMBINING ACUTE
~~~

Cả hai dãy này được Unicode xác định là **canonically equivalent**. `Normalizer.normalize(s, NFC)` giúp gom về dạng nhất quán.

Điều đó không có nghĩa rằng:

- `a` và `á` là một ký tự giống nhau về ý nghĩa.
- `đ` tự động trở thành `d`.
- Mọi dấu thanh có thể xóa mà không mất thông tin tiếng Việt.
- Chuỗi chứa các ký tự trông giống nhau từ bảng chữ cái khác đều bằng nhau.

Đối với tên người, địa chỉ, nội dung tìm kiếm hoặc văn bản hiển thị, **giữ đúng dấu** thường quan trọng. Canonical normalization giúp thống nhất **cách lưu cùng một chữ**, còn **accent-insensitive search** (tìm kiếm không phân biệt dấu) là một **chính sách tra cứu khác** có thể tạo ra nhiều kết quả cùng khóa và phải được thiết kế riêng.

### Vì sao so sánh có thể gây lỗi dù giao diện trông giống nhau?

Giả sử hệ thống đã lưu một khóa `"café"` ở dạng dựng sẵn, còn dữ liệu import gửi `"cafe\u0301"`. Nếu dùng trực tiếp:

~~~java
// Minh họa bên trong một phương thức:
java.util.Set<String> names = new java.util.HashSet<>();
names.add("caf\u00E9");
boolean found = names.contains("cafe\u0301"); // false
~~~

`HashSet` dựa vào `equals` và `hashCode` của `String`; nó không nhận biết canonical equivalence. Để kiểm tra theo quy tắc NFC, chuẩn hóa **cả khóa khi lưu và giá trị khi tra**.

## 8. Áp dụng vào tìm kiếm, so sánh, Map và database

### 8.1. Một helper chuẩn hóa NFC, dùng nhất quán

~~~java
// Mảnh mã có thể đặt trong một lớp tiện ích:
static String nfc(String value) {
    return java.text.Normalizer.normalize(
            value, java.text.Normalizer.Form.NFC);
}
~~~

Giả định hệ thống có chính sách không chấp nhận `null` cho trường này. Nếu trường cho phép `null`, hãy xử lý riêng theo hợp đồng ứng dụng; không biến `null` thành chuỗi rỗng một cách tùy tiện.

### 8.2. HashMap/Set: chuẩn hóa ở cả hai phía

~~~java
java.util.Set<String> keys = new java.util.HashSet<>();
keys.add(nfc("caf\u00E9"));

boolean found = keys.contains(nfc("cafe\u0301"));
// found == true
~~~

**Quy tắc:** chuẩn hóa một phía mà bỏ phía còn lại là một lỗi thường gặp. Nếu đã dùng NFC làm khóa định danh, mọi thao tác **ghi, đọc, tìm kiếm, sửa, kiểm tra trùng** phải tuân thủ cùng chính sách.

### 8.3. Database và chỉ mục

Trong hệ thống thực tế, một trường văn bản có thể có:

- **Giá trị gốc:** giữ nguyên đúng dữ liệu do người dùng nhập, phục vụ hiển thị, audit hoặc khôi phục.
- **Giá trị chuẩn hóa:** dùng NFC làm khóa tìm kiếm/trùng lặp khi nghiệp vụ định nghĩa canonical-equivalent strings là cùng một giá trị.

Ví dụ lược đồ khái niệm:

~~~text
display_name = dữ liệu người dùng nhập
name_nfc     = Normalizer.normalize(display_name, NFC)
~~~

Khi truy vấn, tính `nfc(query)` trước rồi tra `name_nfc`. Nếu database có collation, unique index hoặc normalization riêng, **kiểm tra chính sách của chính database**. Không giả định so sánh Java `String.equals`, toán tử SQL `=` và quy tắc collation của database luôn giống nhau.

Với hệ thống đã có dữ liệu, thay đổi chính sách normalization có thể ảnh hưởng khóa duy nhất: hai giá trị trước đây khác nhau có thể trùng nhau sau NFC. Cần kiểm kê các collision và quyết định cách hợp nhất **theo nghiệp vụ** trước khi đặt unique constraint trên cột chuẩn hóa.

### 8.4. Hash và cache

Nếu dùng chuỗi làm cache key, dữ liệu cấp trước khi chuẩn hóa và sau khi chuẩn hóa có thể tạo **hai key khác nhau**. Chuẩn hóa ở điểm vào và tái sử dụng một hợp đồng khóa rõ ràng giúp tránh cache miss do khác biểu diễn Unicode. Đối với khóa định danh từ hệ thống khác, cần tuân theo đặc tả của hệ thống đó trước khi áp dụng bất kỳ normalization nào.

## 9. NFC và NFKC khác gì trong thực tế?

**NFC** thường được ưu tiên khi muốn giữ nguyên nội dung văn bản thông thường nhưng xóa sai biệt về biểu diễn chính tắc. **NFKC** có thể gom thêm các ký tự “tương thích” như ligature, số trong vòng tròn hoặc ký tự fullwidth.

Ví dụ:

~~~java
String circledOne = "\u2460";
String nfc = java.text.Normalizer.normalize(
        circledOne, java.text.Normalizer.Form.NFC);
String nfkc = java.text.Normalizer.normalize(
        circledOne, java.text.Normalizer.Form.NFKC);

System.out.println(nfc.equals(circledOne)); // true
System.out.println(nfkc.equals("1"));       // true
~~~

Với **ký hiệu tài liệu**, người dùng có thể quan tâm đến sự khác biệt giữa **①** và **1**. Nếu lưu đè toàn bộ văn bản ở dạng NFKC, thông tin kiểu trình bày có thể bị mất.

Với **identifier được chuẩn hóa theo chính sách cụ thể**, NFKC đôi khi hữu ích để giảm số cách viết một định danh; nhưng NFKC **không phải** biện pháp bảo mật Unicode đầy đủ, không phát hiện mọi ký tự dễ nhầm và không thay thế kiểm tra mixed-script/confusables. Mọi quyết định phải dựa trên đặc tả identifier hoặc bộ quy tắc được thiết kế cho ứng dụng, đồng thời tính đến các collision sau khi chuẩn hóa.

**Đừng tự áp dụng NFKC cho mật khẩu hoặc token:** đây là những dữ liệu có hợp đồng so khớp rất chặt. Việc chuẩn hóa phải là một phần của **chính sách được công bố và sử dụng đồng nhất**; tự thay đổi normalization có thể khiến credential cũ không còn khớp hoặc làm nhiều đầu vào khác nhau trở thành một giá trị.

## 10. Normalization không đồng nghĩa các phép biến đổi văn bản khác

| Nhu cầu | Normalizer có tự giải quyết? | Cần gì thêm |
| --- | --- | --- |
| Hai chuỗi có cùng nội dung theo **canonical equivalence** | **Có**, khi chuẩn hóa cả hai cùng NFC/NFD | Áp dụng cùng chính sách trên mọi điểm vào |
| Gộp các ký tự có **compatibility mapping** | **Có**, bằng NFKC/NFKD, kèm mất mát thông tin | Quy tắc phù hợp nghiệp vụ |
| So sánh **không phân biệt hoa/thường** | **Không** | Case mapping/case folding phù hợp locale và hợp đồng |
| Tìm kiếm **không phân biệt dấu** | **Không** | Thuật toán/Collator/chỉ mục tìm kiếm riêng, xác định rõ ý nghĩa của dấu |
| Sắp xếp từ điển theo ngôn ngữ | **Không** | Collation (ví dụ `java.text.Collator`, cấu hình locale phù hợp) |
| Phát hiện ký tự giống nhau để chống giả mạo | **Không đầy đủ** | Unicode security/confusable handling theo chính sách |
| Đếm **chữ hiển thị** hoặc cụm emoji | **Không** | Grapheme segmentation phù hợp Unicode |
| Chuyển Unicode thành **byte UTF-8** | **Không** | Charset encoding như `StandardCharsets.UTF_8` |
| Loại khoảng trắng hoặc chuẩn hóa dấu xuống dòng | **Không** | Xử lý whitespace/line endings riêng nếu nghiệp vụ yêu cầu |
| Chuyển chữ Việt sang không dấu | **Không** | Biến đổi/tra cứu chuyên biệt và chấp nhận mất mát ngữ nghĩa |

Ví dụ, gọi `Normalizer.normalize("Café", NFC)` **không làm chữ `C` thành `c`**, và không loại dấu sắc khỏi `é`. Muốn tìm kiếm không phân biệt chữ hoa/thường, cần một quy tắc bổ sung; nhưng `toLowerCase(Locale.ROOT)` cũng **không phải toàn bộ thuật toán Unicode case folding** cho mọi hệ chữ, vì thế không thể thay mọi chính sách so khớp chỉ bằng một lời gọi lowercase.

Tương tự, chiến lược “NFD rồi xóa toàn bộ combining marks” làm mất dấu và có thể thay đổi nghĩa, nhất là với tiếng Việt; nó cũng **không tự xử lý** các ký tự như `đ`. Chỉ làm như vậy nếu bài toán tìm kiếm thực sự cho phép, và vẫn giữ bản gốc khi cần.

## 11. Các đặc tính quan trọng của normalize

### 11.1. Idempotence: chuẩn hóa lại cùng form không thay đổi kết quả

Với một form `F`, phép chuẩn hóa được thiết kế để thỏa:

~~~text
normalize(normalize(s, F), F) == normalize(s, F)
~~~

Đây là so sánh **nội dung chuỗi**, không phải so sánh tham chiếu đối tượng bằng `==`. Trong Java hãy dùng `equals`.

### 11.2. Cùng canonical-equivalence, cùng NFC/NFD

Nếu hai dãy Unicode **canonically equivalent**, đưa cả hai về NFC hoặc NFD theo cùng phiên bản/đặc tả phù hợp sẽ cho cùng dãy kết quả. Đây là cơ sở để kiểm tra trùng và làm khóa nhất quán.

Ngược lại, **không** thể suy ra rằng những dãy có glyph nhìn giống nhau đều canonically equivalent.

### 11.3. Unicode có quy tắc ổn định chuẩn hóa, nhưng dữ liệu mới vẫn cần lưu ý

Unicode định nghĩa các bảo đảm ổn định của normalization cho những ký tự đã được gán trong các phiên bản tiêu chuẩn tương ứng. Tuy nhiên, một runtime cũ có thể chưa biết các code point được bổ sung ở phiên bản Unicode mới. Vì thế khi trao đổi dữ liệu qua hệ thống nhiều phiên bản, cần biết **phiên bản Unicode mà runtime/database hỗ trợ**, đặc biệt nếu hệ thống đòi tính nhất quán tuyệt đối của các bộ dữ liệu mới.

### 11.4. Chuẩn hóa không tự sửa dữ liệu không hợp lệ

Normalizer hoạt động theo quy tắc Unicode; nó không chứng minh dữ liệu đúng chính tả, đúng tiếng Việt, không chứa ký tự điều khiển bất thường hoặc an toàn để hiển thị vào HTML/SQL. Các bước **validation, escaping, charset handling và business rules** vẫn độc lập.

## 12. Quy trình triển khai đề xuất cho trường văn bản cần so khớp ổn định

1. **Xác định quan hệ bằng nhau:** nghiệp vụ cần so khớp byte, UTF-16 chính xác, canonical-equivalent, compatibility-equivalent, không phân biệt hoa/thường hay theo collation ngôn ngữ? Không chọn form trước khi xác định yêu cầu.
2. **Chọn chính sách cho từng trường dữ liệu:** tên hiển thị thường giữ bản gốc và có thể có khóa NFC; mã/token/password cần theo đặc tả riêng; danh mục tìm kiếm có thể có khóa phụ phù hợp.
3. **Chuẩn hóa tại điểm vào đã chọn:** ví dụ nhận dữ liệu từ API rồi tạo `Normalizer.normalize(value, NFC)` trước khi lưu khóa.
4. **Chuẩn hóa cả phía truy vấn:** cùng form và những quy tắc bổ sung theo **đúng thứ tự** đã định; không để các luồng nhập liệu khác nhau có chính sách khác nhau.
5. **Giữ bản gốc khi cần:** để trình bày đúng, phân tích lỗi hoặc hỗ trợ xử lý collision.
6. **Kiểm tra collision trước khi tạo unique constraint:** nhiều dạng khác nhau có thể thành một khóa; quyết định xử lý dựa vào nghiệp vụ.
7. **Viết test với văn bản tiếng Việt, ký tự kết hợp, ký tự compatibility và emoji:** test cả dữ liệu Unicode lẫn việc display/so sánh.
8. **Kiểm tra tích hợp database/cache/search:** có thể chúng có collation hoặc quy tắc riêng, không nhất thiết cùng `String.equals`.

Một helper hữu ích cho khóa NFC:

~~~java
// Ví dụ hàm trong một lớp Java; input phải khác null:
static String normalizedKey(String input) {
    return java.text.Normalizer.normalize(
            input, java.text.Normalizer.Form.NFC);
}
~~~

Khi tạo `Map` hoặc kiểm tra trùng, dùng hàm này **cả lúc tạo khóa lẫn lúc lookup**. Không dùng `==` để so sánh nội dung `String`.

## 13. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Giao diện hiển thị giống nhau thì `equals` phải đúng” | Glyph không quyết định dãy UTF-16 | So sánh sau cùng normalization phù hợp |
| “NFC là bỏ dấu tiếng Việt” | NFC giữ canonical equivalence và dấu có ý nghĩa | Dùng NFC để thống nhất biểu diễn; tìm không dấu là chính sách khác |
| “NFKC luôn tốt hơn NFC” | NFKC có thể xóa các khác biệt compatibility | Cân nhắc mất mát và collision trước khi dùng |
| “Một code point là một chữ người dùng nhìn thấy” | Combining marks/emoji có thể tạo grapheme cluster nhiều code point | Phân biệt code point, code unit, grapheme |
| “`String.length()` đếm số ký tự hiển thị” | Nó đếm UTF-16 code units | Dùng công cụ phân đoạn Unicode nếu cần grapheme |
| “Chuẩn hóa khi lưu là đủ” | Truy vấn chưa chuẩn hóa có thể không khớp | Áp dụng cùng chính sách cả hai phía |
| “Normalizer đồng thời xử lý hoa/thường, dấu, tìm kiếm, bảo mật” | Đây là các bài toán khác nhau | Tách rõ normalization, case mapping, collation, confusable detection |
| “Cứ chuẩn hóa NFKC là không cần kiểm tra identifier” | NFKC không loại mọi ký tự dễ nhầm | Kết hợp chính sách ký tự, kiểm tra input và security profile |
| “Dùng `==` để so sánh chuỗi đã chuẩn hóa” | `==` so sánh tham chiếu | Dùng `equals` |
| “Bất kỳ văn bản nào nên chuẩn hóa và ghi đè ngay” | Có trường cần giữ bản gốc hoặc tương thích hệ thống ngoài | Phân loại trường, lưu bản gốc/khóa chuẩn hóa khi cần |

## 14. Bài tập kiểm tra hiểu biết

**Câu 1.** Hai chuỗi `"\u00E9"` và `"e\u0301"` có thể hiển thị như nhau. Tại sao `equals` trả về `false`?

**Đáp án:** chúng có các dãy UTF-16 khác nhau; chuỗi thứ nhất có một code point dựng sẵn, chuỗi thứ hai có chữ `e` và một combining mark. `String.equals` không tự làm Unicode normalization.

**Câu 2.** Muốn lưu tên tiếng Việt không mất dấu nhưng thống nhất các biểu diễn canonically equivalent, nên xét dạng nào?

**Đáp án:** **NFC** là lựa chọn thường phù hợp cho văn bản thông thường; áp dụng nhất quán và giữ bản gốc nếu sản phẩm cần.

**Câu 3.** `Normalizer.normalize("①", NFKC)` và `Normalizer.normalize("①", NFC)` có nhất thiết bằng nhau không?

**Đáp án:** **Không**. NFKC chuyển ký tự U+2460 sang chữ số `1`; NFC giữ ký tự số trong vòng tròn.

**Câu 4.** Nếu một ứng dụng muốn tìm kiếm tên không phân biệt dấu tiếng Việt, chỉ gọi `Normalizer.normalize(name, NFC)` đã đủ chưa?

**Đáp án:** **Chưa**. NFC giữ dấu, chỉ thống nhất biểu diễn tương đương chính tắc. Tìm kiếm không phân biệt dấu cần một chính sách tìm kiếm bổ sung và đánh đổi về ý nghĩa.

**Câu 5.** Đặt chuỗi chưa chuẩn hóa vào `HashSet` và truy vấn bằng chuỗi NFC có bảo đảm tìm thấy không?

**Đáp án:** **Không**. `HashSet` so theo `hashCode`/`equals` của giá trị thật. Cả ghi và đọc phải dùng cùng dạng chuẩn hóa nếu muốn canonically-equivalent strings chung khóa.

**Câu 6.** Có nên NFKC mọi password và token khi nhận từ người dùng để “tăng bảo mật” không?

**Đáp án:** Không tự ý làm vậy. Các hệ thống xác thực và token có đặc tả so khớp riêng; thay đổi quy tắc có thể khiến giá trị khác nhau trùng nhau hoặc làm xác thực thất bại. Chỉ dùng normalization nếu hợp đồng hệ thống quy định rõ và được thực hiện nhất quán.

## 15. Tài liệu tham khảo chính thức

- **Java SE 17 — `java.text.Normalizer`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- **Java SE 17 — `Normalizer.Form`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.Form.html
- **Unicode Standard Annex #15 — Unicode Normalization Forms:** https://unicode.org/reports/tr15/
- **Unicode Consortium — Normalization FAQ:** https://unicode.org/faq/normalization.html
- **Unicode Technical Standard #39 — Unicode Security Mechanisms:** https://unicode.org/reports/tr39/

**Kết luận:** `java.text.Normalizer` không sửa hình thức hiển thị, không xóa dấu một cách mặc định và không biến mọi ký tự giống hình thành một ký tự. Nó đưa văn bản về **một trong bốn dạng chuẩn hóa Unicode được định nghĩa rõ ràng**. Khi cần so khớp cùng nội dung chính tắc, hãy chọn NFC (hoặc NFD theo yêu cầu), chuẩn hóa **hai phía** và kiểm tra collision; chỉ dùng NFKC/NFKD khi ứng dụng thật sự cho phép xóa các phân biệt tương thích.
